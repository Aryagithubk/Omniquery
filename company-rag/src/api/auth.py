from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
from typing import Optional
import jwt
import re
import psycopg2
from passlib.context import CryptContext
from datetime import datetime, timedelta

from src.config.config_loader import load_config
from src.utils.logger import setup_logger

logger = setup_logger("Auth")

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = "supersecret_omniquery_key"  # In production, read from env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours — prevents role fallback mid-session

class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid email format")
        return v.lower().strip()

class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    department_id: int
    job_title: str
    salary: float
    hire_date: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid email format")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) < 1:
            raise ValueError("Name cannot be empty")
        return v.strip()

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    first_name: str = ""
    last_name: str = ""
    email: str = ""

config = load_config("config.yaml")

def get_db_connection():
    db_url = config.get("agents", {}).get("db_agent", {}).get("db_url", "postgresql://omniquery:omniquery123@localhost:5432/omniquery_demo")
    import re as re_mod
    pattern = r"postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<dbname>.+)"
    match = re_mod.match(pattern, db_url)
    if not match:
        raise ValueError("Invalid database URL")
    
    conn_params = match.groupdict()
    return psycopg2.connect(
        host=conn_params.get("host"),
        port=int(conn_params.get("port")),
        user=conn_params.get("user"),
        password=conn_params.get("password"),
        dbname=conn_params.get("dbname"),
    )

def ensure_password_hash_column():
    """
    Startup migration: ensures the employees table has a password_hash column.
    This is idempotent — safe to call on every startup.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'employees' AND column_name = 'password_hash';
        """)
        if not cursor.fetchone():
            logger.info("Auth migration: Adding 'password_hash' column to employees table...")
            cursor.execute("ALTER TABLE employees ADD COLUMN password_hash VARCHAR(256);")
            conn.commit()
            logger.info("Auth migration: 'password_hash' column added successfully.")
        else:
            logger.info("Auth migration: 'password_hash' column already exists. ✓")
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Auth migration check failed: {e}")

# Run migration check on module import
ensure_password_hash_column()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

import hashlib

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email, password_hash, role, first_name, last_name FROM employees WHERE email = %s;",
            (req.email,)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

        # Check password hash
        stored_hash = user[2]
        if not stored_hash or hashlib.sha256(req.password.encode()).hexdigest() != stored_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
            
        first_name = user[4] or ""
        last_name = user[5] or ""
        role = user[3] or "user"
        
        token = create_access_token(data={
            "sub": user[1],
            "role": role,
            "full_name": f"{first_name} {last_name}".strip(),
        })
        return {
            "access_token": token,
            "role": role,
            "first_name": first_name,
            "last_name": last_name,
            "email": user[1],
        }
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if email exists
        cursor.execute("SELECT id FROM employees WHERE email = %s;", (req.email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already taken"
            )
            
        hashed_pw = hashlib.sha256(req.password.encode()).hexdigest()
        
        # Insert user (default role is 'user')
        cursor.execute(
            """INSERT INTO employees 
               (first_name, last_name, email, department_id, job_title, salary, hire_date, password_hash, role) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'user') RETURNING id;""",
            (req.first_name, req.last_name, req.email, req.department_id, req.job_title, req.salary, req.hire_date, hashed_pw)
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # Auto-login the specific user
        token = create_access_token(data={
            "sub": req.email,
            "role": "user",
            "full_name": f"{req.first_name} {req.last_name}".strip(),
        })
        return {
            "access_token": token,
            "role": "user",
            "first_name": req.first_name,
            "last_name": req.last_name,
            "email": req.email,
        }
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "username": payload.get("sub"),
            "role": payload.get("role", "user"),
            "full_name": payload.get("full_name", ""),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid auth token")

# For testing getting the current user if needed directly
def get_current_user(token_data: dict = Depends(verify_token)):
    return token_data
