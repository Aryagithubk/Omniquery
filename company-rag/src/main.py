"""
OmniQuery — Multi-Agent AI System
Main entry point with FastAPI server and LangGraph orchestrator.
"""

import os
import sys
import time

# Ensure project root is on the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List

from src.config.config_loader import load_config
from src.llm.provider_factory import LLMProviderFactory
from src.agents.agent_registry import AgentRegistry
from src.agents.doc_agent.agent import DocAgent
from src.agents.db_agent.agent import DBAgent
from src.agents.confluence_agent.agent import ConfluenceAgent
from src.agents.web_agent.agent import WebSearchAgent
from src.core.orchestrator.router import AgentRouter
from src.core.orchestrator.graph import build_orchestrator_graph
from src.utils.logger import setup_logger
from src.api import auth

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

security = HTTPBearer(auto_error=False)

logger = setup_logger("OmniQuery")

# ──────────────────────────────────────────────
# Load Configuration
# ──────────────────────────────────────────────

config = load_config("config.yaml")

# ──────────────────────────────────────────────
# Initialize LLM Provider
# ──────────────────────────────────────────────

llm_provider = LLMProviderFactory.create(config.get("llm", {}))

# ──────────────────────────────────────────────
# Initialize Agents
# ──────────────────────────────────────────────

registry = AgentRegistry()

# DocAgent
doc_config = config.get("agents", {}).get("doc_agent", {})
if doc_config.get("enabled", True):
    doc_agent = DocAgent(
        config={
            "embedding_model": config.get("embedding", {}).get("model", "nomic-embed-text"),
            "persist_directory": config.get("vector_db", {}).get("persist_directory", "./vector_store"),
            "top_k": config.get("app", {}).get("top_k", 3),
        },
        llm_provider=llm_provider,
    )
    registry.register(doc_agent)

# DBAgent
db_config = config.get("agents", {}).get("db_agent", {})
if db_config.get("enabled", True):
    db_agent = DBAgent(
        config={
            "db_url": db_config.get("db_url", "postgresql://omniquery:omniquery123@localhost:5432/omniquery_demo"),
            "db_type": db_config.get("db_type", "postgresql"),
        },
        llm_provider=llm_provider,
    )
    registry.register(db_agent)

# ConfluenceAgent
confluence_config = config.get("agents", {}).get("confluence_agent", {})
if confluence_config.get("enabled", False):
    confluence_agent = ConfluenceAgent(
        config={
            "base_url": confluence_config.get("base_url", ""),
            "username": confluence_config.get("username", ""),
            "api_token": confluence_config.get("api_token", ""),
            "spaces": confluence_config.get("spaces", []),
            "max_results": confluence_config.get("max_results", 5),
        },
        llm_provider=llm_provider,
    )
    registry.register(confluence_agent)

# WebSearchAgent
web_config = config.get("agents", {}).get("web_agent", {})
if web_config.get("enabled", True):
    web_agent = WebSearchAgent(
        config={
            "max_results": web_config.get("max_results", 5),
        },
        llm_provider=llm_provider,
    )
    registry.register(web_agent)

# ──────────────────────────────────────────────
# Build Orchestrator
# ──────────────────────────────────────────────

orchestrator_config = config.get("orchestrator", {})
router = AgentRouter(
    agents=registry.get_all(),
    min_confidence=orchestrator_config.get("min_agent_confidence", 0.3),
    max_parallel=orchestrator_config.get("max_parallel_agents", 2),
)

orchestrator = build_orchestrator_graph(router, registry, llm_provider)

# ──────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────

app = FastAPI(
    title="OmniQuery",
    description="Multi-Agent AI Query System",
    version="2.0.0",
)

# CORS — allow frontend to reach backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
static_dir = os.path.join(web_dir, "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    logger.warning(f"Static files directory not found: {static_dir}")

app.include_router(auth.router)


# ──────────────────────────────────────────────
# Startup Event
# ──────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize all agents on server startup"""
    logger.info("🚀 OmniQuery starting up... initializing agents.")
    await registry.initialize_all()
    agents = registry.get_all()
    for a in agents:
        logger.info(f"  → {a.name}: {a._status.value}")
    logger.info(f"✅ OmniQuery ready — {len(agents)} agent(s) registered.")


# ──────────────────────────────────────────────
# API Models
# ──────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str


class SourceCitation(BaseModel):
    agent_name: str
    source_type: str
    source_identifier: str
    relevance_score: float = 0.0
    excerpt: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceCitation] = []
    agents_used: List[str] = []
    confidence: float = 0.0
    execution_time_ms: float = 0.0


# ──────────────────────────────────────────────
# API Routes
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    html_path = os.path.join(web_dir, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

@app.get("/auth", response_class=HTMLResponse)
async def serve_auth_page():
    html_path = os.path.join(web_dir, "auth.html")
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.post("/api/v1/query", response_model=QueryResponse)
async def query(request: QueryRequest, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Process a query through the multi-agent orchestrator"""
    start_time = time.time()
    logger.info(f"📥 Query: '{request.query[:100]}...'")

    # Extract user role from token (default to 'user' if not provided or invalid)
    user_role = "user"
    if credentials:
        try:
            payload = jwt.decode(credentials.credentials, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
            user_role = payload.get("role", "user")
        except jwt.ExpiredSignatureError:
            # Token expired but still readable — extract role without enforcing expiry.
            # This prevents superadmins from silently being demoted to 'user'.
            try:
                payload = jwt.decode(
                    credentials.credentials, auth.SECRET_KEY,
                    algorithms=[auth.ALGORITHM],
                    options={"verify_exp": False}
                )
                user_role = payload.get("role", "user")
                logger.warning(f"Token expired — role '{user_role}' preserved from payload. User should re-login soon.")
            except Exception:
                logger.warning("Token expired and unreadable — defaulting to 'user' role.")
        except Exception as e:
            logger.warning(f"Failed to decode token: {e}")

    try:
        # Run the orchestrator graph
        initial_state = { 
            "query": request.query,
            "original_query": request.query, 
            "session_id": "",
            "intent": "",
            "user_role": user_role,
            "entities": {},
            # DB-specific state — populated by classify node
            "db_intent": None,
            "db_permission_denied_reason": None,
            "db_fast_path": None,
            "primary_agent": None,
            "agent_plans": [],
            "current_agent_index": 0,
            "agent_results": [],
            "failed_agents": [],
            "synthesized_answer": "",
            "final_sources": [],
            "agents_used": [],
            "overall_confidence": 0.0,
            "formatted_response": "",
            "execution_time_ms": 0.0,
            "error": None,
        }# hrr ek query k liye ye object banega aur data isme add hote rhega sb iska use krke apna data dalenge aur fir jb formetted response store ho jayega to fire return kr dega 

        result = await orchestrator.ainvoke(initial_state) # ye h wo graph jo state ko use krke apna data dalega aur fir jb formetted response store ho jayega to fire return kr dega  , hamne await use kiya h because isme time lagega sb process hokr aane me hmm

        exec_time = (time.time() - start_time) * 1000
        # structure of result
        # {
        #     "query": "...",
        #     "original_query": "...",
        #     "session_id": "...",
        #     "intent": "...",
        #     "entities": {...},
        #     "agent_plans": [...],
        #     "current_agent_index": 0,
        #     "agent_results": [...],
        #     "failed_agents": [...],
        #     "synthesized_answer": "...",
        #     "final_sources": [...],
        #     "agents_used": [...],
        #     "overall_confidence": 0.0,
        #     "formatted_response": "...",
        #     "execution_time_ms": 0.0,
        #     "error": None,
        # }
        # structure of final_sources
        # [
        #     {
        #         "agent_name": "...",
        #         "source_type": "...",
        #         "source_identifier": "...",
        #         "relevance_score": 0.0,
        #         "excerpt": "...",
        #     },
        #     {
        #         "agent_name": "...",
        #         "source_type": "...",
        #         "source_identifier": "...",
        #         "relevance_score": 0.0,
        #         "excerpt": "...",
        #     },
        # ]
        # Build sources, a = {"agent_name": "...", "source_type": "...", "source_identifier": "...", "relevance_score": 0.0, "excerpt": "..."}, a.agent_name, a.get("agent_name", "Unknown")
        sources = []
        for s in result.get("final_sources", []): # yha final_sources ek list h aur usme se ek ek element le rhe h  jisa use krke hame sare source dekh rhe aur uska use kr rhe 
            sources.append(SourceCitation(
                agent_name=s.get("agent_name", "Unknown"), # yha "unknown" default value h agar agent_name nhi mila to ye print hoga 
                source_type=s.get("source_type", "unknown"),
                source_identifier=s.get("source_identifier", ""),
                relevance_score=s.get("relevance_score", 0.0),
                excerpt=s.get("excerpt"),
            ))


        answer = result.get("formatted_response", "") or result.get("synthesized_answer", "No answer.")
        agents_used = result.get("agents_used", [])
        confidence = result.get("overall_confidence", 0.0)

        logger.info(f"📤 Response via {agents_used} (confidence: {confidence}, {exec_time:.0f}ms)")

        return QueryResponse(# wuery response banane k liye hame asnwer, sources, agent_used, confidence, execution_time_ms ye s chaiye to uper ham result se le rhe h aur return kr rhe h final
            answer=answer,
            sources=sources,
            agents_used=agents_used,
            confidence=confidence,
            execution_time_ms=round(exec_time, 1),
        )

    except Exception as e:
        logger.error(f"❌ Orchestrator error: {e}")
        return QueryResponse(
            answer=f"Sorry, I encountered an error: {str(e)}",
            execution_time_ms=(time.time() - start_time) * 1000,
        )


@app.get("/api/v1/agents")
async def list_agents():#
    """Get all agents and their health status"""
    health = await registry.health_check_all()
    return {"agents": health}


# ──────────────────────────────────────────────
# Also keep the legacy /query endpoint for backward compat
# ──────────────────────────────────────────────

@app.post("/query")
async def legacy_query(request: QueryRequest):
    """Legacy endpoint — redirects to /api/v1/query"""
    return await query(request)


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    server_cfg = config.get("server", {})
    uvicorn.run(
        app,
        host=server_cfg.get("host", "localhost"),
        port=server_cfg.get("port", 8000),
    )
