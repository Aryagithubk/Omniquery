"""
Seed Script — Populates the PostgreSQL database with realistic demo data.
Creates tables: departments, employees, projects
Run: python scripts/seed_postgres.py
"""

import psycopg2
import sys

# ── Connection Settings ──
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "omniquery",
    "password": "omniquery123",
    "dbname": "omniquery_demo",
}


def seed():
    print("🔌 Connecting to PostgreSQL...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\n💡 Make sure PostgreSQL is running. Start it with:")
        print("   docker run -d --name omniquery-pg \\")
        print("     -e POSTGRES_USER=omniquery \\")
        print("     -e POSTGRES_PASSWORD=omniquery123 \\")
        print("     -e POSTGRES_DB=omniquery_demo \\")
        print("     -p 5432:5432 \\")
        print("     postgres:16-alpine")
        sys.exit(1)

    # ── Drop existing tables (fresh start) ──
    print("🗑️  Dropping existing tables...")
    cursor.execute("DROP TABLE IF EXISTS projects CASCADE;")
    cursor.execute("DROP TABLE IF EXISTS employees CASCADE;")
    cursor.execute("DROP TABLE IF EXISTS departments CASCADE;")
    cursor.execute("DROP TABLE IF EXISTS users CASCADE;")

    # ── Create departments ──
    print("📋 Creating departments table...")
    cursor.execute("""
        CREATE TABLE departments (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            location VARCHAR(100) NOT NULL,
            budget NUMERIC(12,2) NOT NULL
        );
    """)

    departments = [
        ("Engineering",   "Building A, Floor 3",  1500000.00),
        ("Marketing",     "Building B, Floor 1",   800000.00),
        ("Sales",         "Building B, Floor 2",   950000.00),
        ("Human Resources", "Building A, Floor 1", 600000.00),
        ("Finance",       "Building A, Floor 2",   700000.00),
        ("Product",       "Building C, Floor 1",   900000.00),
        ("Design",        "Building C, Floor 2",   550000.00),
        ("DevOps",        "Building A, Floor 4",   650000.00),
    ]
    cursor.executemany(
        "INSERT INTO departments (name, location, budget) VALUES (%s, %s, %s);",
        departments,
    )
    print(f"   ✅ Inserted {len(departments)} departments")

    # ── Create employees ──
    print("👤 Creating employees table...")
    cursor.execute("""
        CREATE TABLE employees (
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(50) NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            email VARCHAR(100) NOT NULL UNIQUE,
            department_id INTEGER REFERENCES departments(id),
            job_title VARCHAR(100) NOT NULL,
            salary NUMERIC(10,2) NOT NULL,
            hire_date DATE NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user'
        );
    """)

    import hashlib
    hash_pw = hashlib.sha256("password".encode()).hexdigest()

    employees = [
        # Engineering (dept 1)
        ("Arjun",   "Sharma",    "arjun.sharma@company.com",    1, "Senior Software Engineer",  125000.00, "2021-03-15", True, hash_pw, "superadmin"),
        ("Priya",   "Patel",     "priya.patel@company.com",     1, "Software Engineer",          95000.00, "2022-06-01", True, hash_pw, "admin"),
        ("Rahul",   "Kumar",     "rahul.kumar@company.com",     1, "Tech Lead",                 145000.00, "2019-01-10", True, hash_pw, "user"),
        ("Sneha",   "Reddy",     "sneha.reddy@company.com",     1, "Junior Developer",           72000.00, "2023-09-20", True, hash_pw, "user"),
        ("Vikram",  "Singh",     "vikram.singh@company.com",    1, "Backend Developer",         105000.00, "2020-11-05", True, hash_pw, "user"),
        ("Ananya",  "Gupta",     "ananya.gupta@company.com",    1, "Frontend Developer",         98000.00, "2022-02-14", True, hash_pw, "user"),
        ("Karan",   "Mehta",     "karan.mehta@company.com",     1, "DevOps Engineer",           110000.00, "2021-07-22", False, hash_pw, "user"),
        # Marketing (dept 2)
        ("Neha",    "Verma",     "neha.verma@company.com",      2, "Marketing Manager",         115000.00, "2020-04-12", True, hash_pw, "user"),
        ("Amit",    "Joshi",     "amit.joshi@company.com",      2, "Content Strategist",         85000.00, "2022-08-30", True, hash_pw, "user"),
        ("Divya",   "Nair",      "divya.nair@company.com",      2, "SEO Specialist",             78000.00, "2023-01-18", True, hash_pw, "user"),
        ("Ravi",    "Rao",       "ravi.rao@company.com",         2, "Digital Marketing Lead",    105000.00, "2021-05-25", True, hash_pw, "user"),
        # Sales (dept 3)
        ("Pooja",   "Iyer",      "pooja.iyer@company.com",      3, "Sales Director",            140000.00, "2018-09-03", True, hash_pw, "user"),
        ("Suresh",  "Menon",     "suresh.menon@company.com",    3, "Account Executive",          92000.00, "2021-12-01", True, hash_pw, "user"),
        ("Meera",   "Chatterjee","meera.chatterjee@company.com",3, "Sales Representative",       75000.00, "2023-04-10", True, hash_pw, "user"),
        ("Deepak",  "Mishra",    "deepak.mishra@company.com",   3, "Sales Manager",             120000.00, "2020-02-28", True, hash_pw, "user"),
        ("Kavita",  "Desai",     "kavita.desai@company.com",    3, "Business Development",       88000.00, "2022-10-15", True, hash_pw, "user"),
        # HR (dept 4)
        ("Sanjay",  "Kapoor",    "sanjay.kapoor@company.com",   4, "HR Director",               130000.00, "2017-06-15", True, hash_pw, "user"),
        ("Anjali",  "Thakur",    "anjali.thakur@company.com",   4, "HR Specialist",              82000.00, "2022-03-20", True, hash_pw, "user"),
        ("Manish",  "Saxena",    "manish.saxena@company.com",   4, "Recruiter",                  76000.00, "2023-07-01", True, hash_pw, "user"),
        # Finance (dept 5)
        ("Ritika",  "Bhatt",     "ritika.bhatt@company.com",    5, "Finance Manager",           125000.00, "2019-08-12", True, hash_pw, "user"),
        ("Arun",    "Pandey",    "arun.pandey@company.com",     5, "Financial Analyst",          90000.00, "2021-11-30", True, hash_pw, "user"),
        ("Swati",   "Kulkarni",  "swati.kulkarni@company.com",  5, "Accountant",                 72000.00, "2023-02-14", True, hash_pw, "user"),
        # Product (dept 6)
        ("Nikhil",  "Goyal",     "nikhil.goyal@company.com",    6, "Product Manager",           135000.00, "2020-01-20", True, hash_pw, "user"),
        ("Shruti",  "Agarwal",   "shruti.agarwal@company.com",  6, "Product Analyst",            88000.00, "2022-05-10", True, hash_pw, "user"),
        ("Vivek",   "Chauhan",   "vivek.chauhan@company.com",   6, "Product Owner",             120000.00, "2020-09-15", True, hash_pw, "user"),
        # Design (dept 7)
        ("Ishaan",  "Bhatia",    "ishaan.bhatia@company.com",   7, "Lead Designer",             110000.00, "2021-04-08", True, hash_pw, "user"),
        ("Tanvi",   "Srivastava","tanvi.srivastava@company.com",7, "UI/UX Designer",             92000.00, "2022-07-22", True, hash_pw, "user"),
        ("Rohan",   "Malhotra",  "rohan.malhotra@company.com",  7, "Graphic Designer",           78000.00, "2023-06-01", True, hash_pw, "user"),
        # DevOps (dept 8)
        ("Gaurav",  "Tiwari",    "gaurav.tiwari@company.com",   8, "DevOps Lead",               130000.00, "2019-10-10", True, hash_pw, "user"),
        ("Pallavi", "Jain",      "pallavi.jain@company.com",    8, "Cloud Engineer",            115000.00, "2021-08-18", True, hash_pw, "user"),
        ("Mohit",   "Yadav",     "mohit.yadav@company.com",     8, "SRE Engineer",              108000.00, "2022-01-05", True, hash_pw, "user"),
    ]
    cursor.executemany(
        """INSERT INTO employees
           (first_name, last_name, email, department_id, job_title, salary, hire_date, is_active, password_hash, role)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);""",
        employees,
    )
    print(f"   ✅ Inserted {len(employees)} employees")

    # ── Create projects ──
    print("📂 Creating projects table...")
    cursor.execute("""
        CREATE TABLE projects (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            department_id INTEGER REFERENCES departments(id),
            lead_employee_id INTEGER REFERENCES employees(id),
            budget NUMERIC(12,2) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            start_date DATE NOT NULL,
            end_date DATE
        );
    """)

    projects = [
        ("OmniQuery AI Platform",        1, 3,  350000.00, "active",    "2024-01-15", None),
        ("Cloud Migration Phase 2",      8, 29, 280000.00, "active",    "2024-03-01", None),
        ("Brand Refresh Campaign",       2, 8,  120000.00, "completed", "2023-06-01", "2024-02-28"),
        ("Mobile App Redesign",          7, 26, 180000.00, "active",    "2024-02-01", None),
        ("Sales Automation Tool",        3, 12, 200000.00, "active",    "2024-04-01", None),
        ("Employee Wellness Platform",   4, 17,  95000.00, "planning",  "2024-06-01", None),
        ("Financial Dashboard v3",       5, 20, 150000.00, "active",    "2023-11-01", None),
        ("Product Analytics Engine",     6, 23, 250000.00, "active",    "2024-01-20", None),
        ("DevSecOps Pipeline",           8, 30, 175000.00, "completed", "2023-04-01", "2024-01-15"),
        ("Customer Portal Revamp",       1, 1,  220000.00, "planning",  "2024-07-01", None),
    ]
    cursor.executemany(
        """INSERT INTO projects
           (name, department_id, lead_employee_id, budget, status, start_date, end_date)
           VALUES (%s, %s, %s, %s, %s, %s, %s);""",
        projects,
    )
    print(f"   ✅ Inserted {len(projects)} projects")

    # ── Summary ──
    cursor.execute("SELECT COUNT(*) FROM departments;")
    dept_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM employees;")
    emp_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM projects;")
    proj_count = cursor.fetchone()[0]


    cursor.close()
    conn.close()

    print("\n" + "=" * 50)
    print("✅ Database seeded successfully!")
    print(f"   🔐 Accounts (Employees): {emp_count}")
    print(f"   📋 Departments: {dept_count}")
    print(f"   👤 Employees:   {emp_count}")
    print(f"   📂 Projects:    {proj_count}")
    print("=" * 50)
    print("\n💡 Try these queries in OmniQuery:")
    print('   • "How many employees are there?"')
    print('   • "What is the average salary by department?"')
    print('   • "List all active projects"')
    print('   • "Who has the highest salary?"')
    print('   • "Show me the Engineering department budget"')


if __name__ == "__main__":
    seed()
