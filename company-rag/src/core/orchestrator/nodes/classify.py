"""
Classify node — classifies the query intent and routes to agents.
Uses the AgentRouter to score agents and build an execution plan.
Also performs RBAC-aware DB intent detection: if the user lacks permission
for a mutation (INSERT/UPDATE/DELETE), the plan is short-circuited here
before any agent executes.

INTENT DETECTION uses a weighted-scoring approach instead of first-match
to ensure the most relevant intent wins (e.g. "company policy" → document_search,
not web_search).

GUARDRAILS prevent DB-unrelated queries (real-time events, public facts,
stock prices, current news) from ever reaching the DBAgent.
"""

import re
from typing import Optional, Tuple
from src.core.orchestrator.state import OmniQueryState
from src.utils.logger import setup_logger

logger = setup_logger("ClassifyNode")

# ── RBAC Permission Matrix ─────────────────────────────────────────────────────
# Maps user_role → frozenset of allowed db_intent values
_RBAC_PERMISSIONS = {
    "user":       frozenset(["select"]),
    "admin":      frozenset(["select", "update"]),
    "superadmin": frozenset(["select", "update", "insert", "delete"]),
}

# ── Mutation keyword groups (order matters — more specific first) ──────────────
_DELETE_KEYWORDS = [
    "delete", "remove", "drop", "erase", "purge", "terminate", "fire",
    "dismiss", "eliminate",
]
_INSERT_KEYWORDS = [
    "insert", "add", "create", "register", "onboard", "hire", "new employee",
    "add employee", "add new",
]
_UPDATE_KEYWORDS = [
    "update", "change", "modify", "set", "assign", "promote", "demote",
    "transfer", "adjust", "edit", "rename", "increase", "decrease",
    "upgrade", "downgrade", "grant", "revoke", "make", "move",
    # Role-specific verbs (ensure role-change queries are always classified as update)
    "change role", "change the role", "update role", "update the role",
    "set role", "set the role", "assign role", "assign the role",
    "make admin", "make superadmin", "make user",
]

# ── Real-time query patterns — these must NEVER go to DBAgent ─────────────────
# Used as a hard guardrail in both intent classification and can_handle scoring.
_REAL_TIME_PATTERNS = [
    r"\b(stock|share)\s+(price|value|rate)\b",
    r"\bprice\s+of\s+\w+\b",
    r"\b(current|today'?s?|latest|live|real.?time)\b.*\b(price|rate|value|news|update)\b",
    r"\bwho\s+(is|are|was|were)\s+the\s+(current\s+)?(president|prime\s+minister|ceo|mayor|chancellor|king|queen|leader)\b",
    r"\b(oscar|emmy|grammy|tony|bafta|golden\s+globe)\b",
    r"\b(award|winner|won|nominated)\b.*\b(this\s+year|2024|2025|2026)\b",
    r"\b(news|breaking|headline|trending|viral)\b",
    r"\b(weather|forecast|temperature)\b",
    r"\bwho\s+(won|won\s+the)\b",
    r"\b(latest|current|recent)\b.*\b(event|news|update|development)\b",
    r"\bright\s+now\b",
    r"\bas\s+of\s+(today|now|this\s+(week|month|year))\b",
    r"\bwhat\s+is\s+(happening|going\s+on)\b",
    r"\bgoogle\b",                   # explicit "google X" → web search
    r"\bsearch\s+(the\s+web|online|internet|for)\b",
]

# ── DB-presence signal: if NONE of these appear, query is not DB-related ──────
_DB_PRESENCE_SIGNALS = [
    "employee", "employe", "salary", "database", "table", "department",
    "dept", "record", "query", "budget", "project", "manager", "staff",
    "worker", "hire", "fire", "promote", "demote", "role update", "insert",
    "delete employee", "add employee", "remove employee", "count employee",
    "how many employee",
    # Role-change signals — any query mentioning role + an action word is a DB op
    "change role", "change the role", "update role", "update the role",
    "set role", "set the role", "assign role", "make admin", "make superadmin",
]

# Also detect DB presence from email address pattern (any query with user@domain.com
# is almost certainly targeting a specific internal employee record)
_EMAIL_PATTERN = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')

# ── Intent keyword groups with weights ─────────────────────────────────────────
# Higher weight = stronger signal for that intent category
_INTENT_KEYWORDS = {
    "data_query": {
        "keywords": [
            "how many", "count", "total", "average", "salary", "employee",
            "employees", "employe", "employes", "eployee", "eployees",
            "database", "table", "department", "project", "budget",
            "manager", "revenue", "customer", "order", "highest", "lowest", "sum",
            "list all", "show me all", "show all", "get all", "find all",
            "maximum", "minimum",
            "update", "insert", "delete", "add employee",
            "remove employee", "change salary", "promote", "demote",
            "hire", "fire", "assign", "modify", "onboard", "job title",
            "contact", "email", " db", "db ", "record", "records",
            "fetch", "display", "staff", "worker",
            # Role mutation keywords (missing before — caused misrouting to WebSearch)
            "role", "change role", "change the role", "update role", "update the role",
            "set role", "set the role", "assign role", "assign the role",
            "make admin", "make superadmin", "make user",
            "grant admin", "revoke admin", "grant role", "revoke role",
        ],
        "weight": 1.0,
        "base_score": 0.0,
    },
    "document_search": {
        "keywords": [
            "document", "policy", "procedure", "guideline", "handbook",
            "standard", "leave", "expense", "onboarding", "company",
            "rules", "internal", "report", "file", "pdf", "manual",
            "benefit", "benefits", "vacation", "work from home", "wfh",
            "attendance", "code of conduct", "compliance", "regulation",
            "terms", "conditions", "health", "safety", "insurance",
            "holiday", "holidays", "pto", "sick leave", "maternity",
            "paternity", "hr policy", "hr policies", "compensation",
            "reimbursement", "travel policy", "dress code",
        ],
        "weight": 1.2,
        "base_score": 0.0,
    },
    "summarization": {
        "keywords": [
            "summarize", "summary", "explain", "what does", "overview",
            "brief", "tldr", "recap",
        ],
        "weight": 1.0,
        "base_score": 0.0,
    },
    "wiki_search": {
        "keywords": [
            "wiki", "confluence", "knowledge base", "runbook",
        ],
        "weight": 1.5,
        "base_score": 0.0,
    },
    "real_time": {
        # High-signal real-time / public-knowledge queries that belong on the web
        "keywords": [
            "stock price", "share price", "current price", "live price",
            "stock value", "market cap", "trading at",
            "who is the president", "who is the prime minister", "who is the ceo",
            "who is the mayor", "who is the chancellor",
            "oscar", "oscar winner", "academy award", "grammy", "emmy", "bafta",
            "golden globe", "award winner", "who won",
            "breaking news", "latest news", "current events", "trending",
            "weather", "forecast",
            "google", "search the web", "search online", "search internet",
            "search for", "find on the internet",
            "right now", "as of today", "as of now",
            "current events", "what is happening",
            "president of", "prime minister of", "leader of",
            "population of", "capital of", "currency of",
        ],
        "weight": 1.5,    # Strong signal — real-time queries are very specific
        "base_score": 0.0,
    },
    "web_search": {
        "keywords": [
            "search the web", "search online", "google", "internet",
            "latest news", "current events", "trending", "breaking",
            "search for",
        ],
        "weight": 1.0,
        "base_score": 0.0,
    },
}

# ── Fast-Path Detection Patterns ──────────────────────────────────────────────
# Regex patterns for queries that can be answered with a direct SQL query
_FAST_PATH_PATTERNS = [
    # "show me all employees", "list all employees", etc.
    (r"\b(show|list|get|fetch|display|give)\b.*\b(all)\b.*\b(employee|employees|employes|employess|eployee|eployees|staff|worker|people)\b",
     "SELECT id, first_name, last_name, email, job_title, department_id, role, salary FROM employees"),
    # "how many employees", "count employees", "total employees"
    (r"\b(how many|count|total number of|total)\b.*\b(employee|employees|employes|employess|eployee|eployees|staff|worker|people)\b",
     "SELECT COUNT(*) AS total_employees FROM employees"),
    # "show all departments", "list departments"
    (r"\b(show|list|get|fetch|display|give)\b.*\b(all)\b.*\b(department|departments)\b",
     "SELECT * FROM departments"),
    # "show all projects", "list projects"
    (r"\b(show|list|get|fetch|display|give)\b.*\b(all)\b.*\b(project|projects)\b",
     "SELECT * FROM projects"),
    # "average salary", "mean salary"
    (r"\b(average|avg|mean)\b.*\b(salary|salaries|pay)\b",
     "SELECT ROUND(AVG(salary)::numeric, 2) AS average_salary FROM employees"),
    # "highest salary", "top salary", "maximum salary"
    (r"\b(highest|top|maximum|max|best)\b.*\b(salary|salaries|paid|earning)\b",
     "SELECT id, first_name, last_name, email, job_title, salary FROM employees ORDER BY salary DESC LIMIT 5"),
    # "lowest salary", "minimum salary"
    (r"\b(lowest|bottom|minimum|min|least)\b.*\b(salary|salaries|paid|earning)\b",
     "SELECT id, first_name, last_name, email, job_title, salary FROM employees ORDER BY salary ASC LIMIT 5"),
    # "all employee details", "employee details", "all details"
    (r"\b(all)\b.*\b(detail|details|data|information|info)\b",
     "SELECT id, first_name, last_name, email, job_title, department_id, role, salary FROM employees"),
    # "show me employees" (without "all" but clearly wants list)
    (r"\b(show|list|display|give me|tell me)\b.*\b(employee|employees|employes|employess|eployee|eployees)\b.*\b(detail|details|data|record|records)\b",
     "SELECT id, first_name, last_name, email, job_title, department_id, role, salary FROM employees"),
]

# ── Dynamic Fast-Path Patterns ────────────────────────────────────────────────
_DYNAMIC_FAST_PATH_PATTERNS = [
    (r"\b(top|best|highest)\b\s+(\d+)\s+\b(employee|employees|employes|employess|eployee|eployees|staff|worker|workers|people)\b",
     "SELECT id, first_name, last_name, email, job_title, department_id, salary FROM employees ORDER BY salary DESC LIMIT {n}"),
    (r"\b(bottom|lowest|worst|least)\b\s+(\d+)\s+\b(employee|employees|employes|employess|eployee|eployees|staff|worker|workers|people)\b",
     "SELECT id, first_name, last_name, email, job_title, department_id, salary FROM employees ORDER BY salary ASC LIMIT {n}"),
    (r"\b(give|show|list|get|fetch|display)\b\s+(?:me\s+)?(\d+)\s+\b(employee|employees|employes|employess|eployee|eployees|staff|worker|workers|people)\b",
     "SELECT id, first_name, last_name, email, job_title, department_id, salary FROM employees ORDER BY salary DESC LIMIT {n}"),
]


def _is_real_time_query(query: str) -> bool:
    """
    Hard guardrail: returns True if the query matches any known real-time/
    public-knowledge pattern. These queries MUST NOT go to the DBAgent.
    """
    q = query.lower()
    for pattern in _REAL_TIME_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return True
    return False


def _has_db_presence_signal(query: str) -> bool:
    """
    Returns True if the query contains at least one signal that it
    is about internal employee/database data.
    Includes an email address detector: any query referencing user@domain.com
    is almost certainly targeting an internal employee record.
    """
    q = query.lower()
    if any(signal in q for signal in _DB_PRESENCE_SIGNALS):
        return True
    # Email address in query → definitely a DB/employee operation
    if _EMAIL_PATTERN.search(query):
        return True
    return False


def _detect_fast_path(query: str) -> Optional[str]:
    """
    Check if the query matches a known fast-path pattern.
    Returns the SQL query to execute directly, or None.
    """
    q = query.lower().strip()

    for pattern, sql in _FAST_PATH_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            logger.info(f"Fast-path detected: pattern='{pattern[:40]}...' → SQL='{sql[:60]}...'")
            return sql

    for pattern, sql_template in _DYNAMIC_FAST_PATH_PATTERNS:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            n = int(m.group(2))
            n = max(1, min(n, 100))
            sql = sql_template.format(n=n)
            logger.info(f"Dynamic fast-path detected: N={n} → SQL='{sql[:80]}...'")
            return sql

    return None


def _detect_db_intent(query: str) -> str:
    """
    Detect the DB operation type from the query text.
    Returns: "delete" | "insert" | "update" | "select"
    Uses word-boundary (\\b) regex matching to avoid false positives.
    """
    q = query.lower()

    def _word_match(keywords: list, text: str) -> bool:
        return any(re.search(r'\b' + re.escape(kw) + r'\b', text) for kw in keywords)

    if _word_match(_DELETE_KEYWORDS, q):
        return "delete"
    if _word_match(_INSERT_KEYWORDS, q):
        return "insert"
    if _word_match(_UPDATE_KEYWORDS, q):
        return "update"
    return "select"


def _check_db_rbac(db_intent: str, user_role: str) -> Tuple[bool, str]:
    """
    Check if the user_role is allowed to perform db_intent.
    Returns (is_allowed, denial_reason).
    """
    role = user_role.lower() if user_role else "user"
    allowed = _RBAC_PERMISSIONS.get(role, _RBAC_PERMISSIONS["user"])

    if db_intent not in allowed:
        role_caps = {
            "user": "read-only (SELECT) access",
            "admin": "SELECT and UPDATE access",
            "superadmin": "full access (SELECT, INSERT, UPDATE, DELETE)",
        }
        op_upper = db_intent.upper()
        reason = (
            f"⛔ **Permission Denied**: Your role (`{role}`) only has "
            f"{role_caps.get(role, 'limited')} to the database. "
            f"The `{op_upper}` operation requires a higher privilege level. "
            f"Please contact your system administrator."
        )
        return False, reason

    return True, ""


def _classify_intent(query: str) -> Tuple[str, str]:
    """
    Weighted-scoring intent classification.
    Returns (intent, primary_agent).

    Priority order:
      1. Hard guardrail: real-time pattern match → always "real_time"
      2. Weighted keyword scoring across all intent categories
      3. If no score and no DB signal → "real_time" (web fallback)
      4. If no score but has DB signal → "data_query"
    """
    q = query.lower()

    # ── PRIORITY 1: Hard real-time guardrail ─────────────────────────────────
    # Queries matching real-time patterns bypass scoring entirely.
    if _is_real_time_query(query):
        logger.info(f"Real-time guardrail triggered for query: '{query[:60]}' → intent='real_time'")
        return "real_time", "WebSearchAgent"

    # ── PRIORITY 2: Weighted scoring ─────────────────────────────────────────
    scores = {}
    for intent_name, config in _INTENT_KEYWORDS.items():
        score = config["base_score"]
        for kw in config["keywords"]:
            if kw in q:
                score += config["weight"]
        scores[intent_name] = score

    best_intent = "general"
    best_score = 0.0
    for intent_name, score in scores.items():
        if score > best_score:
            best_score = score
            best_intent = intent_name

    # ── PRIORITY 3: Zero-score fallback ──────────────────────────────────────
    if best_score == 0.0:
        if _has_db_presence_signal(query):
            best_intent = "data_query"
            logger.info("Zero-score with DB signal → forcing data_query")
        else:
            # No score, no DB signal → general public knowledge → web search
            best_intent = "real_time"
            logger.info("Zero-score, no DB signal → routing to real_time (WebSearchAgent)")

    # ── Merge real_time and web_search into same agent ────────────────────────
    # real_time scores might tie or lose to web_search; both go to WebSearchAgent
    if best_intent in ("real_time", "web_search"):
        best_intent = "real_time"

    # ── Determine primary agent ───────────────────────────────────────────────
    intent_to_agent = {
        "data_query":      "DBAgent",
        "document_search": "DocAgent",
        "summarization":   "DocAgent",
        "wiki_search":     "ConfluenceAgent",
        "real_time":       "WebSearchAgent",
        "web_search":      "WebSearchAgent",
        "general":         "WebSearchAgent",   # General → web, not DocAgent (internal docs only)
    }
    primary_agent = intent_to_agent.get(best_intent, "WebSearchAgent")

    logger.info(
        f"Intent scores: {', '.join(f'{k}={v:.1f}' for k, v in scores.items())} "
        f"→ best='{best_intent}' (score={best_score:.1f}), primary_agent='{primary_agent}'"
    )

    return best_intent, primary_agent


def make_classify_node(router):
    """Factory that creates classify node with access to the router"""

    async def classify_node(state: OmniQueryState) -> dict:
        """Classify intent, detect DB operation, enforce RBAC, then build agent routing plan"""
        from src.agents.base_agent import AgentContext

        query = state["query"]
        user_role = state.get("user_role", "user")
        logger.info(f"Classifying query: '{query[:80]}' | role={user_role}")

        # 1. Classify the broad intent using weighted scoring + real-time guardrail
        intent, primary_agent = _classify_intent(query)

        # 2. If it's a data query, detect the specific DB operation, fast-path, and enforce RBAC
        db_intent = None
        db_permission_denied_reason = None
        db_fast_path = None

        if intent == "data_query":
            db_intent = _detect_db_intent(query)
            is_allowed, denial_reason = _check_db_rbac(db_intent, user_role)

            if not is_allowed:
                logger.warning(
                    f"RBAC BLOCK: role='{user_role}' attempted db_intent='{db_intent}' — denied."
                )
                return {
                    "intent": intent,
                    "primary_agent": primary_agent,
                    "db_intent": "permission_denied",
                    "db_permission_denied_reason": denial_reason,
                    "db_fast_path": None,
                    "agent_plans": [],
                    "current_agent_index": 0,
                }

            logger.info(f"RBAC PASS: role='{user_role}' → db_intent='{db_intent}' ✓")

            if db_intent == "select":
                db_fast_path = _detect_fast_path(query)
                if db_fast_path:
                    logger.info(f"DB fast-path set: '{db_fast_path[:60]}...'")

        # 3. Build agent context and route to agents
        context = AgentContext(
            query=query,
            original_query=state.get("original_query", query),
            intent=intent,
            session_id=state.get("session_id", ""),
            user_role=user_role,
            entities={"db_intent": db_intent} if db_intent else {},
        )

        plans = await router.route(context)

        # 4. Reorder plans so primary_agent is first (if it's in the list)
        if primary_agent and plans:
            primary_plans = [p for p in plans if p["agent_name"] == primary_agent]
            other_plans = [p for p in plans if p["agent_name"] != primary_agent]
            if primary_plans:
                plans = primary_plans + other_plans
                for i, plan in enumerate(plans):
                    plan["priority"] = i + 1
                logger.info(f"Reordered plans: primary_agent='{primary_agent}' moved to front.")

        if not plans:
            logger.warning("No agents matched — will use fallback.")

        return {
            "intent": intent,
            "primary_agent": primary_agent,
            "db_intent": db_intent,
            "db_permission_denied_reason": db_permission_denied_reason,
            "db_fast_path": db_fast_path,
            "agent_plans": plans,
            "current_agent_index": 0,
        }

    return classify_node
