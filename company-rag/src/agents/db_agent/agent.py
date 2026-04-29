"""
DBAgent - Tool-equipped ReAct Agent with Direct Execution Fast-Path.
Participates in the LangGraph orchestrator the same way as DocAgent:
  preprocess → classify (RBAC guard) → execute_agent → synthesize → format

Three execution paths:
  1. Fast-path: Direct SQL for simple SELECT queries (list all, counts, etc.)
  2. Mutation path: Guided LLM→SQL flow for INSERT/UPDATE/DELETE (no ReAct)
  3. ReAct path: Full ReAct loop for complex/ambiguous SELECT queries

RBAC is enforced at TWO layers:
  1. Classify node  → blocks disallowed operations before any agent runs
  2. DBAgentTools   → enforces role limits inside execute_custom_mutation (defence-in-depth)
"""

import re
import time
import json
import sqlalchemy
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import create_engine, text

from src.agents.base_agent import BaseAgent, AgentContext, AgentResponse, AgentStatus
from src.utils.logger import setup_logger
from src.config.prompt_loader import PromptLoader
from src.agents.react_engine import ReActEngine, Tool
from src.agents.db_agent.tools import DBAgentTools

logger = setup_logger("DBAgent")




class DBAgent(BaseAgent):
    """
    Agent that queries/mutates the PostgreSQL database.
    Participates fully in the LangGraph orchestrator pipeline.
    RBAC is handled upstream in the classify node; this agent
    only executes operations that have already been authorised.
    """

    def __init__(self, config: Dict[str, Any], llm_provider: Any):
        super().__init__(config, llm_provider)
        self._name = "DBAgent"
        self.db_url = config.get("db_url", "")
        self.schema_info = ""
        self.engine = None
        self.tools_handler = None

        # Load externalized prompts
        self.prompt_config = PromptLoader().load_prompt("db_agent")

    def _parse_db_url(self, url: str) -> Dict[str, str]:
        """Parse postgresql://user:pass@host:port/dbname into connection params"""
        pattern = r"postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<dbname>.+)"
        match = re.match(pattern, url)
        if match:
            return match.groupdict()
        return {}

    @property
    def description(self) -> str:
        return "Answers data questions and performs authorised database mutations (INSERT/UPDATE/DELETE) based on user role."

    @property
    def supported_intents(self) -> List[str]:
        # "db_mutation" is set when classify detected a write operation
        return ["data_query", "analytics", "reporting", "database", "db_mutation"]

    async def initialize(self) -> None:
        """Connect to PostgreSQL, initialise SQLAlchemy engine, introspect schema, and setup tools."""
        try:
            self.engine = create_engine(self.db_url)
            self.tools_handler = DBAgentTools(self.engine)

            schema_parts = []
            with self.engine.connect() as conn:
                tables = conn.execute(sqlalchemy.text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                """)).fetchall()

                table_names = [t[0] for t in tables]

                for table_name in table_names:
                    columns = conn.execute(sqlalchemy.text("""
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                        ORDER BY ordinal_position;
                    """), {"table_name": table_name}).fetchall()

                    col_defs = ", ".join(
                        [f"{c[0]} ({c[1]}, nullable={c[2]})" for c in columns]
                    )
                    schema_parts.append(f"Table '{table_name}': columns = [{col_defs}]")

            self.schema_info = "\n".join(schema_parts)

            if not table_names:
                self._status = AgentStatus.ERROR
                logger.warning("DBAgent: No tables found in PostgreSQL database.")
            else:
                self._status = AgentStatus.READY
                logger.info(f"DBAgent initialized — found {len(table_names)} table(s).")

        except Exception as e:
            self._status = AgentStatus.ERROR
            logger.error(f"DBAgent init failed: {e}")

    async def can_handle(self, context: AgentContext) -> float:
        """
        Confidence scoring based on DB-related and mutation keywords.
        Mutation queries are scored very high (0.95) to ensure DBAgent always
        wins routing when a write operation is detected.

        INTENT GUARDS:
        - Returns 0.0 immediately for real_time/web_search intents — these are
          public-knowledge queries (stock prices, Oscar winners, world leaders)
          that must NEVER reach the DBAgent.
        - Returns 0.0 for document_search/summarization intents to prevent
          DBAgent from stealing DocAgent's policy/HR queries.
        """
        if self._status != AgentStatus.READY:
            return 0.0

        # ── HARD INTENT GUARDS ──────────────────────────────────────────────
        # Real-time and web queries have nothing to do with the internal DB.
        if context.intent in ("real_time", "web_search"):
            logger.info(
                f"DBAgent: HARD BLOCK — intent='{context.intent}' is a web/real-time query. "
                "Returning 0.0 to prevent incorrect routing."
            )
            return 0.0

        # Document/summarization queries belong to DocAgent.
        if context.intent in ("document_search", "summarization"):
            logger.info(f"DBAgent: intent='{context.intent}' — applying score penalty.")
            score = -0.1
        else:
            score = 0.3

        query_lower = context.query.lower()

        # Specific DB-domain keywords (intentionally narrow — no generic words)
        db_keywords = [
            "employee", "employe", "eployee", "eployees", "employes",
            "salary", "database", "table",
            "count", "how many", "list all", "average", "total",
            "department", "dept", "record", "query",
            "highest", "lowest", "maximum", "minimum", "sum",
            "project", "projects", "budget", "status", "manager",
            "show me all", "get all", "find all",
            "staff", "worker",
            "fetch", "display",
            "job title", "contact", "email", " db", "db ",
        ]
        mutation_keywords = [
            "update", "insert", "delete", "create", "drop", "alter",
            "add employee", "remove employee", "change salary", "change role",
            "set salary", "set role", "assign role",
            "promote", "demote", "make admin", "grant", "revoke",
            "hire", "fire", "onboard", "transfer", "adjust salary",
        ]

        data_matches = sum(1 for kw in db_keywords if kw in query_lower)
        mutation_matches = sum(1 for kw in mutation_keywords if kw in query_lower)
        matches = data_matches + mutation_matches

        if mutation_matches >= 2:
            score = 0.95   # Very confident — clear mutation intent
        elif mutation_matches == 1 and data_matches >= 1:
            score = 0.90   # Mutation + data context — high confidence
        elif mutation_matches == 1:
            score = 0.75   # Single mutation keyword — still prioritise
        elif matches >= 3:
            score += 0.6
        elif matches >= 2:
            score += 0.4
        elif matches == 1:
            score += 0.3

        # db_intent passed from classify node (if available in context.entities)
        db_intent = context.entities.get("db_intent")
        if db_intent in ("update", "insert", "delete"):
            score = max(score, 0.95)

        if context.intent in ["data_query", "analytics", "reporting", "database", "db_mutation"]:
            score = min(score + 0.1, 1.0)

        return min(score, 1.0)


    def _execute_direct_sql(self, sql: str) -> Tuple[bool, str, float]:
        """
        Execute a SQL query directly (no ReAct loop) and return formatted results.
        Returns (success, formatted_answer, confidence).
        Used for fast-path queries detected by the classify node.
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql))
                rows = [dict(row._mapping) for row in result]

                # Convert non-serializable types
                for r in rows:
                    for k, v in r.items():
                        if not isinstance(v, (int, float, str, bool, type(None))):
                            r[k] = str(v)

                if not rows:
                    return True, "No data found.", 0.3

                # Format as markdown table
                md_table = self.tools_handler._format_markdown_table(rows, "Query Results")
                confidence = min(0.95, 0.7 + (len(rows) * 0.01))  # Higher confidence for more rows
                return True, md_table, confidence

        except Exception as e:
            logger.error(f"Direct SQL execution error: {e}")
            return False, f"Database error: {str(e)}", 0.0


    # ── Helpers ────────────────────────────────────────────────────────────────

    def _make_sources(self, confidence: float, excerpt: str) -> List[Dict]:
        """Build standardized source metadata for agent responses."""
        return [{
            "agent_name": self.name,
            "source_type": "database",
            "source_identifier": f"PostgreSQL: {self._parse_db_url(self.db_url).get('dbname', 'unknown')}",
            "relevance_score": confidence,
            "excerpt": excerpt,
        }]

    def _extract_employee_name(self, query: str) -> Optional[str]:
        """
        Best-effort extraction of an employee name from a mutation query.
        Strips known action/filler/field words and returns the first 2 remaining tokens.
        Returns None if no plausible name could be extracted.
        """
        q = query.lower()

        # Remove email addresses (these are values, not names)
        q = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', '', q)

        # Remove numbers, special chars — keep only letters and spaces
        q = re.sub(r'[^a-z\s]', ' ', q)

        # Noise words to strip (action words, SQL keywords, common fillers)
        noise = {
            # Action verbs
            'update', 'change', 'modify', 'set', 'edit', 'delete', 'remove',
            'insert', 'add', 'create', 'fire', 'dismiss', 'terminate', 'erase',
            'purge', 'promote', 'demote', 'transfer', 'adjust', 'assign',
            'grant', 'revoke', 'onboard', 'rename', 'increase', 'decrease',
            # Articles, prepositions, conjunctions
            'the', 'of', 'to', 'as', 'for', 'from', 'in', 'on', 'at', 'by',
            'an', 'a', 'and', 'or', 'not', 'be', 'is', 'are', 'into', 'with',
            'his', 'her', 'their', 'my', 'this', 'that', 'it',
            # Domain nouns / field names
            'employee', 'employees', 'detail', 'details', 'record', 'data',
            'db', 'database', 'table', 'email', 'salary', 'role', 'department',
            'job', 'title', 'name', 'first', 'last', 'id', 'all', 'new',
            'row', 'column', 'value', 'field', 'one', 'info', 'information',
            'active', 'inactive', 'hire', 'date', 'company', 'com',
            # Common filler verbs
            'please', 'can', 'you', 'want', 'need', 'like', 'give', 'make',
            'put', 'show', 'get', 'fetch', 'tell', 'me',
            # Role names (to avoid confusing "admin" with a person's name)
            'admin', 'superadmin', 'user', 'true', 'false',
        }

        tokens = q.split()
        filtered = [t for t in tokens if t not in noise and len(t) > 1]

        # Take at most first 2 tokens as the name
        name = ' '.join(filtered[:2]).strip()
        return name if name else None


    # ── Main Execute ──────────────────────────────────────────────────────────

    async def execute(self, context: AgentContext) -> AgentResponse:
        """
        Execute the DB query or mutation.

        The orchestrator pipeline guarantees that by the time this method is called:
          - RBAC has already been checked in the classify node
          - `context.user_role` carries the authenticated role
          - `context.entities["db_intent"]` carries the detected operation type
            ("select" | "insert" | "update" | "delete")

        Three execution paths:
          PATH 1 — Fast-path:  Direct SQL for simple SELECT queries
          PATH 2 — Mutation:   Guided LLM→SQL for INSERT/UPDATE/DELETE (bypasses ReAct)
          PATH 3 — ReAct:      Full ReAct loop for complex/ambiguous SELECT queries
        """
        start = time.time()
        
        # Read db_intent injected by the execute node from state
        db_intent = context.entities.get("db_intent", "select")
        user_role = context.user_role.lower() if context.user_role else "user"
        db_fast_path = context.entities.get("db_fast_path")

        logger.info(
            f"DBAgent.execute() | role='{user_role}' | db_intent='{db_intent}' "
            f"| fast_path={'YES' if db_fast_path else 'NO'} | query='{context.query[:80]}...'"
        )

        # ── PATH 1: FAST-PATH — Direct SQL execution for simple queries ────
        if db_fast_path:
            logger.info(f"DBAgent FAST-PATH: executing SQL directly → '{db_fast_path[:80]}...'")
            success, answer, confidence = self._execute_direct_sql(db_fast_path)

            return AgentResponse(
                success=success,
                answer=answer,
                confidence=confidence,
                sources=[{
                    "agent_name": self.name,
                    "source_type": "database",
                    "source_identifier": f"PostgreSQL: {self._parse_db_url(self.db_url).get('dbname', 'unknown')}",
                    "relevance_score": confidence,
                    "excerpt": f"Direct SQL fast-path: {db_fast_path[:100]}",
                }],
                execution_time_ms=(time.time() - start) * 1000,
            )

        # ── PATH 2: MUTATION — Guided LLM→SQL for INSERT/UPDATE/DELETE ─────
        # Bypasses the ReAct loop entirely. The ReAct engine's markdown
        # short-circuit causes mutations to fail (it returns lookup results
        # before the mutation tool is ever called). This guided flow is
        # more reliable, especially with small local LLMs (1B parameters).
        if db_intent in ("insert", "update", "delete"):
            self.tools_handler.current_role = user_role
            logger.info(f"DBAgent: Routing to mutation handler for db_intent='{db_intent}'")
            return await self._handle_mutation(context, db_intent, user_role, start)

        # ── PATH 3: REACT — ReAct loop for complex SELECT queries ──────────
        logger.info(f"DBAgent dynamically executing via ReAct loop (db_intent='{db_intent}')")

        if not getattr(self, "prompt_config", None):
            self.prompt_config = PromptLoader().load_prompt("db_agent")

        try:
            # Set role on tools_handler for the second layer of RBAC defence
            self.tools_handler.current_role = user_role

            # Build concise, role-aware instructions for the system prompt
            role_instructions = self._build_role_instructions(user_role, db_intent)

            # Substitute schema, role instructions, and db_intent into the system prompt
            system_prompt = self.prompt_config.get("system_prompt", "You are an AI.")
            system_prompt = system_prompt.format(
                schema_info=self.schema_info,
                role_instructions=role_instructions,
                db_intent=db_intent,
            )

            tools = [
                Tool(
                    name="get_employee_record",
                    description='MANDATORY STRATEGY for individuals: You MUST use this tool to search for specific people or a person\'s details. Pass the person\'s name or email into "search_term". Example Input: {"search_term": "Pooja Iyer"}. NEVER use this for "all", "list", or "top" queries!',
                    func=self.tools_handler.get_employee_record
                ),
                Tool(
                    name="update_employee_role",
                    description="Changes an employee's access role. Requires 'email' and 'new_role' (user, admin, superadmin).",
                    func=self.tools_handler.update_employee_role
                ),
                Tool(
                    name="execute_custom_select",
                    description='DO NOT USE THIS TOOL for finding individual people (no WHERE email=... or WHERE name=...). ONLY use this tool for aggregations (count, average) or fetching ALL records. Example 1: {"query": "SELECT COUNT(*) FROM employees"}. Example 2: {"query": "SELECT * FROM employees"}',
                    func=self.tools_handler.execute_custom_select
                ),
                Tool(
                    name="execute_custom_mutation",
                    description='Executes database mutations. You MUST write raw PostgreSQL in "query". Example Update: {"query": "UPDATE employees SET first_name = \'Prince\', last_name = \'Singh\' WHERE first_name = \'Prince\'"}. Example Delete: {"query": "DELETE FROM employees WHERE id = 1"}.',
                    func=self.tools_handler.execute_custom_mutation
                ),
            ]

            react_engine = ReActEngine(llm=self.llm, tools=tools, max_iterations=5)
            logger.info("Starting ReAct loop for DBAgent...")
            final_answer = await react_engine.execute(system_prompt, context.query)

            # Dynamic confidence based on actual result
            confidence = 0.87  # default
            if not final_answer or "could not determine" in final_answer.lower():
                confidence = 0.2
            elif "no data" in final_answer.lower() or "no matching" in final_answer.lower():
                confidence = 0.4
            elif "|" in final_answer:  # Contains a markdown table
                confidence = 0.92

            # ── FAILURE DETECTION ───────────────────────────────────────────
            # If the ReAct loop produced no useful answer, return success=False
            # so the fallback chain (WebSearchAgent → LLM general knowledge)
            # is triggered correctly by route_after_execute.
            _no_answer_signals = [
                "could not determine",
                "i couldn't find",
                "i could not find",
                "no matching",
                "no data found",
                "no results",
                "i don't have",
                "i do not have",
                "not available",
                "cannot retrieve",
                "unable to retrieve",
            ]
            answer_lower = (final_answer or "").lower()
            is_db_failure = (
                not final_answer
                or confidence < 0.3
                or any(sig in answer_lower for sig in _no_answer_signals)
            )

            if is_db_failure:
                logger.info(
                    f"DBAgent ReAct returned no useful answer (confidence={confidence:.2f}). "
                    "Returning success=False to trigger fallback chain."
                )
                return AgentResponse(
                    success=False,
                    error="DBAgent: no useful answer found in database.",
                    sources=[{
                        "agent_name": self.name,
                        "source_type": "database",
                        "source_identifier": f"PostgreSQL: {self._parse_db_url(self.db_url).get('dbname', 'unknown')}",
                        "relevance_score": confidence,
                        "excerpt": f"ReAct loop produced no useful answer for db_intent='{db_intent}'",
                    }],
                    execution_time_ms=(time.time() - start) * 1000,
                )

            return AgentResponse(
                success=True,
                answer=final_answer,
                confidence=confidence,
                sources=[{
                    "agent_name": self.name,
                    "source_type": "database",
                    "source_identifier": f"PostgreSQL: {self._parse_db_url(self.db_url).get('dbname', 'unknown')}",
                    "relevance_score": confidence,
                    "excerpt": f"ReAct loop executed for db_intent='{db_intent}'",
                }],
                execution_time_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            logger.error(f"DBAgent ReAct execution error: {e}")
            return AgentResponse(
                success=False,
                error=f"Database tool error: {str(e)}",
                execution_time_ms=(time.time() - start) * 1000,
            )


    # ── Mutation Handlers ─────────────────────────────────────────────────────
    # These bypass the ReAct loop entirely. The reason is that the ReAct
    # engine has a "markdown short-circuit" (react_engine.py line 127-133)
    # that returns tool results containing markdown tables immediately,
    # terminating the loop BEFORE any mutation tool is called. This happens
    # because the LLM first calls get_employee_record to look up the target
    # employee, the tool returns markdown, and the loop exits. The mutation
    # never executes. The guided 2-step flow (LLM→SQL → direct execution)
    # avoids this problem entirely.

    async def _handle_mutation(self, context: AgentContext, db_intent: str,
                                user_role: str, start: float) -> AgentResponse:
        """Dispatch to the appropriate mutation handler."""
        try:
            if db_intent == "delete":
                return await self._handle_delete(context, user_role, start)
            elif db_intent == "insert":
                return await self._handle_insert(context, user_role, start)
            elif db_intent == "update":
                return await self._handle_update(context, user_role, start)
            else:
                # Shouldn't reach here; fall through to generic error
                return AgentResponse(
                    success=False,
                    error=f"Unknown mutation type: {db_intent}",
                    sources=self._make_sources(0.0, f"Unknown mutation: {db_intent}"),
                    execution_time_ms=(time.time() - start) * 1000,
                )
        except Exception as e:
            logger.error(f"Mutation handler error ({db_intent}): {e}")
            return AgentResponse(
                success=False,
                error=f"Database mutation error: {str(e)}",
                sources=self._make_sources(0.0, f"Mutation error: {db_intent}"),
                execution_time_ms=(time.time() - start) * 1000,
            )


    async def _handle_delete(self, context: AgentContext, user_role: str,
                              start: float) -> AgentResponse:
        """
        DELETE flow (safety-first):
        - If email is present in query → verify employee exists → execute DELETE
        - If no email (only name) → look up employee → ask user for email confirmation
        This prevents accidental deletion by forcing the user to confirm with
        the employee's unique email identifier.
        """
        query = context.query

        # Check for email in the query
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', query)

        if email_match:
            email = email_match.group(0)

            # Verify employee exists before deleting
            lookup_json = self.tools_handler.get_employee_record(email=email)
            lookup_data = json.loads(lookup_json)

            if lookup_data.get("status") != "success":
                return AgentResponse(
                    success=True,
                    answer=f"❌ No employee found with email `{email}`. Deletion cancelled.",
                    confidence=0.85,
                    sources=self._make_sources(0.85, f"DELETE lookup failed: {email}"),
                    execution_time_ms=(time.time() - start) * 1000,
                )

            # Show who will be deleted
            employee_info = lookup_data.get("markdown", "")

            # Execute delete
            delete_sql = f"DELETE FROM employees WHERE email = '{email}'"
            result_json = self.tools_handler.execute_custom_mutation(query=delete_sql)
            result_data = json.loads(result_json)

            if result_data.get("status") == "success":
                return AgentResponse(
                    success=True,
                    answer=(
                        f"✅ **Employee Deleted Successfully**\n\n"
                        f"{result_data['message']}\n\n"
                        f"**Deleted employee:** `{email}`\n\n"
                        f"**Record that was removed:**\n{employee_info}"
                    ),
                    confidence=0.95,
                    sources=self._make_sources(0.95, f"DELETE executed: {email}"),
                    execution_time_ms=(time.time() - start) * 1000,
                )
            else:
                error_msg = result_data.get("error", "Unknown error")
                return AgentResponse(
                    success=True,
                    answer=f"❌ **Delete Failed**: {error_msg}",
                    confidence=0.4,
                    sources=self._make_sources(0.4, "DELETE failed"),
                    execution_time_ms=(time.time() - start) * 1000,
                )
        else:
            # No email in query — look up employee by name and ask for confirmation
            name = self._extract_employee_name(query)

            if name:
                lookup_json = self.tools_handler.get_employee_record(search_term=name)
                lookup_data = json.loads(lookup_json)

                # ── FUZZY FALLBACK: try split-token search if primary lookup failed ────
                # e.g. "Prince Singh" fails concat-match but "Prince" or "Singh" succeeds
                if lookup_data.get("status") != "success":
                    tokens = [t for t in name.split() if len(t) > 1]
                    for token in tokens:
                        fallback_json = self.tools_handler.get_employee_record(search_term=token)
                        fallback_data = json.loads(fallback_json)
                        if fallback_data.get("status") == "success":
                            lookup_data = fallback_data
                            logger.info(
                                f"DELETE: Primary name lookup failed; "
                                f"token '{token}' matched — using fallback result."
                            )
                            break

                if lookup_data.get("status") == "success":
                    markdown = lookup_data.get("markdown", "")
                    return AgentResponse(
                        success=True,
                        answer=(
                            f"⚠️ **Confirmation Required**\n\n"
                            f"I found the following employee(s) matching **\"{name}\"**:\n\n"
                            f"{markdown}\n\n"
                            f"To proceed with deletion, please provide the **exact email address** "
                            f"of the employee you want to delete.\n\n"
                            f"Example: *\"delete employee ravi.rao@company.com\"*"
                        ),
                        confidence=0.85,
                        sources=self._make_sources(0.85, f"DELETE confirmation requested: {name}"),
                        execution_time_ms=(time.time() - start) * 1000,
                    )
                else:
                    return AgentResponse(
                        success=True,
                        answer=f"❌ No employee found matching **\"{name}\"**. Please check the name and try again.",
                        confidence=0.6,
                        sources=self._make_sources(0.6, f"DELETE: employee not found: {name}"),
                        execution_time_ms=(time.time() - start) * 1000,
                    )
            else:
                return AgentResponse(
                    success=True,
                    answer=(
                        "❌ Please specify which employee to delete by providing their email address.\n\n"
                        "Example: *\"delete employee john.doe@company.com\"*"
                    ),
                    confidence=0.6,
                    sources=self._make_sources(0.6, "DELETE: no identifier provided"),
                    execution_time_ms=(time.time() - start) * 1000,
                )


    async def _handle_insert(self, context: AgentContext, user_role: str,
                              start: float) -> AgentResponse:
        """
        INSERT flow:
        1. Use LLM to generate INSERT SQL from user's natural language description
        2. Validate the generated SQL (must start with INSERT)
        3. Execute it via execute_custom_mutation (RBAC checked there)
        4. Verify by looking up the newly inserted record
        """
        prompt = (
            f"Generate a PostgreSQL INSERT statement for the 'employees' table.\n\n"
            f"The 'employees' table has these columns: id (auto-increment, DO NOT include), "
            f"first_name, last_name, email, department_id, job_title, salary, hire_date, "
            f"is_active, password_hash, role.\n\n"
            f"User request: {context.query}\n\n"
            f"STRICT RULES:\n"
            f"- Output ONLY the raw SQL starting with: INSERT INTO employees ...\n"
            f"- Do NOT include the 'id' column\n"
            f"- Convert all date formats to YYYY-MM-DD (e.g., 12.03.2004 → 2004-03-12)\n"
            f"- If 'role' is not specified, default to 'user'\n"
            f"- If 'password_hash' is not specified, use '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8'\n"
            f"- Use single quotes for all string values\n"
            f"- Split full names into first_name and last_name columns\n"
            f"- Do NOT output any explanation or comments, ONLY the SQL\n\n"
            f"SQL:"
        )

        response = await self.llm.generate(prompt)
        sql = response.text.strip()

        # Clean up LLM output (remove markdown fences, comments, etc.)
        sql = sql.replace("```sql", "").replace("```", "").strip()
        lines = [l.strip() for l in sql.split('\n') if l.strip() and not l.strip().startswith('--')]
        sql = ' '.join(lines)

        # Validate
        if not sql.upper().startswith("INSERT"):
            logger.warning(f"LLM generated non-INSERT SQL: {sql[:100]}")
            return AgentResponse(
                success=True,
                answer=(
                    "❌ Could not generate a valid INSERT query. "
                    "Please provide employee details in a clearer format.\n\n"
                    "Example: *\"add employee John Doe, email john@company.com, "
                    "department_id 1, job title Engineer, salary 100000\"*"
                ),
                confidence=0.3,
                sources=self._make_sources(0.3, "INSERT SQL generation failed"),
                execution_time_ms=(time.time() - start) * 1000,
            )

        logger.info(f"Generated INSERT SQL: {sql}")

        # Execute the mutation (RBAC is enforced inside execute_custom_mutation)
        result_json = self.tools_handler.execute_custom_mutation(query=sql)
        result_data = json.loads(result_json)

        if result_data.get("status") == "success":
            # Verify: look up the newly inserted record by email
            verification = ""
            email_match = re.search(r"'([\w.+-]+@[\w-]+\.[\w.]+)'", sql)
            if email_match:
                try:
                    verify_json = self.tools_handler.get_employee_record(email=email_match.group(1))
                    verify_data = json.loads(verify_json)
                    if verify_data.get("status") == "success":
                        verification = f"\n\n**New Employee Record:**\n{verify_data.get('markdown', '')}"
                except Exception:
                    pass  # Verification is best-effort

            return AgentResponse(
                success=True,
                answer=f"✅ **Employee Inserted Successfully**\n\n{result_data['message']}{verification}",
                confidence=0.95,
                sources=self._make_sources(0.95, f"INSERT executed: {sql[:100]}"),
                execution_time_ms=(time.time() - start) * 1000,
            )
        else:
            error_msg = result_data.get("error", "Unknown error")
            # Make common DB errors more user-friendly
            if "duplicate key" in error_msg.lower() or "unique" in error_msg.lower():
                error_msg = "An employee with this email address already exists."

            return AgentResponse(
                success=True,
                answer=(
                    f"❌ **Insert Failed**: {error_msg}\n\n"
                    f"**Attempted SQL:**\n```sql\n{sql}\n```"
                ),
                confidence=0.4,
                sources=self._make_sources(0.4, "INSERT failed"),
                execution_time_ms=(time.time() - start) * 1000,
            )


    async def _handle_update(self, context: AgentContext, user_role: str,
                              start: float) -> AgentResponse:
        """
        UPDATE flow (two sub-paths):

        SUB-PATH A — Role-change queries (change role, promote, demote, make admin):
          Uses the dedicated update_employee_role() tool which does its own
          existence check and is fully deterministic. Avoids LLM SQL generation
          which caused non-deterministic WHERE clauses and 0-row updates.

        SUB-PATH B — All other field updates (salary, job title, department, etc.):
          1. Extract employee name/email → look up their current record
          2. Provide employee context to LLM for accurate WHERE clause generation
          3. LLM generates UPDATE SQL → validate (must have WHERE clause)
          4. Execute and verify by showing the updated record
        """
        query = context.query
        query_lower = query.lower()

        # ── SUB-PATH A: Role-change detection ──────────────────────────────────
        _role_change_signals = [
            "change role", "change the role", "update role", "update the role",
            "set role", "set the role", "assign role", "assign the role",
            "make admin", "make superadmin", "make user",
            "promote to", "demote to", "grant role", "revoke role",
        ]
        _role_values = ["admin", "superadmin", "user"]

        is_role_change = any(sig in query_lower for sig in _role_change_signals)

        if is_role_change:
            logger.info("DBAgent: Role-change detected — using update_employee_role tool (deterministic path).")

            # Extract email from query (most reliable identifier)
            email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', query)
            target_email = email_match.group(0) if email_match else None

            # If no email, try name lookup
            if not target_email:
                name = self._extract_employee_name(query)
                if name:
                    try:
                        with self.engine.connect() as conn:
                            result = conn.execute(text(
                                "SELECT email FROM employees WHERE "
                                "CONCAT(first_name, ' ', last_name) ILIKE :name LIMIT 1"
                            ), {"name": f"%{name}%"})
                            row = result.fetchone()
                            if row:
                                target_email = row._mapping["email"]
                    except Exception as e:
                        logger.warning(f"Name lookup for role update failed: {e}")

            if not target_email:
                return AgentResponse(
                    success=True,
                    answer=(
                        "❌ Please specify the employee's **email address** to update their role.\n\n"
                        "Example: *\"change the role of john.doe@company.com to admin\"*"
                    ),
                    confidence=0.6,
                    sources=self._make_sources(0.6, "Role update: no email/name provided"),
                    execution_time_ms=(time.time() - start) * 1000,
                )

            # Detect the target role from the query
            new_role = None
            for rv in _role_values:
                if rv in query_lower:
                    new_role = rv
                    break

            if not new_role:
                return AgentResponse(
                    success=True,
                    answer=(
                        f"❌ Could not determine the new role from your request. "
                        f"Valid roles are: `user`, `admin`, `superadmin`.\n\n"
                        f"Example: *\"change the role of {target_email} to admin\"*"
                    ),
                    confidence=0.6,
                    sources=self._make_sources(0.6, "Role update: role value not detected"),
                    execution_time_ms=(time.time() - start) * 1000,
                )

            logger.info(f"Role update: email='{target_email}', new_role='{new_role}'")
            result_json = self.tools_handler.update_employee_role(email=target_email, new_role=new_role)
            result_data = json.loads(result_json)

            if "error" in result_data:
                return AgentResponse(
                    success=True,
                    answer=f"❌ **Role Update Failed**: {result_data['error']}",
                    confidence=0.4,
                    sources=self._make_sources(0.4, "Role update failed"),
                    execution_time_ms=(time.time() - start) * 1000,
                )

            # Success — show the updated record
            verification = ""
            try:
                verify_json = self.tools_handler.get_employee_record(email=target_email)
                verify_data = json.loads(verify_json)
                if verify_data.get("status") == "success":
                    verification = f"\n\n**Updated Record:**\n{verify_data.get('markdown', '')}"
            except Exception:
                pass

            return AgentResponse(
                success=True,
                answer=(
                    f"✅ **Role Updated Successfully**\n\n"
                    f"Employee `{target_email}` has been assigned the role **`{new_role}`**.\n"
                    f"{result_data.get('message', '')}{verification}"
                ),
                confidence=0.95,
                sources=self._make_sources(0.95, f"Role update: {target_email} → {new_role}"),
                execution_time_ms=(time.time() - start) * 1000,
            )

        # ── SUB-PATH B: General field updates (salary, job title, department, etc.) ──

        # Step 1: Try to identify the target employee by name
        employee_context = ""
        employee_name = self._extract_employee_name(query)
        employee_email = None

        if employee_name:
            try:
                with self.engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT id, first_name, last_name, email, job_title, "
                        "department_id, role, salary FROM employees WHERE "
                        "CONCAT(first_name, ' ', last_name) ILIKE :name LIMIT 3"
                    ), {"name": f"%{employee_name}%"})
                    rows = [dict(r._mapping) for r in result]

                    if rows:
                        employee_email = rows[0].get("email")
                        # Convert Decimal to str for formatting
                        for r in rows:
                            if 'salary' in r:
                                r['salary'] = str(r['salary'])
                        md = self.tools_handler._format_markdown_table(rows, "Target Employee")
                        employee_context = (
                            f"\nEmployee found in database:\n{md}\n\n"
                            f"IMPORTANT: Use this employee's current email '{employee_email}' "
                            f"in the WHERE clause for precise targeting.\n"
                        )
                    else:
                        employee_context = (
                            f"\nWARNING: No employee found matching '{employee_name}'. "
                            f"Use first_name/last_name ILIKE for flexible matching in WHERE.\n"
                        )
            except Exception as e:
                logger.warning(f"Employee lookup for update failed: {e}")
                employee_context = "\nCould not pre-identify the target employee.\n"

        # Step 2: Generate UPDATE SQL
        prompt = (
            f"Generate a PostgreSQL UPDATE statement for the 'employees' table.\n\n"
            f"The 'employees' table has these columns: id, first_name, last_name, email, "
            f"department_id, job_title, salary, hire_date, is_active, password_hash, role.\n"
            f"{employee_context}\n"
            f"User request: {query}\n\n"
            f"STRICT RULES:\n"
            f"- Output ONLY the raw SQL starting with: UPDATE employees SET ...\n"
            f"- You MUST update the 'employees' table. Do NOT use any other table.\n"
            f"- ALWAYS include a WHERE clause using the employee's email shown above\n"
            f"- Use single quotes for string values\n"
            f"- Do NOT output any explanation or comments, ONLY the SQL\n\n"
            f"SQL:"
        )

        response = await self.llm.generate(prompt)
        sql = response.text.strip()

        # Clean up LLM output
        sql = sql.replace("```sql", "").replace("```", "").strip()
        lines = [l.strip() for l in sql.split('\n') if l.strip() and not l.strip().startswith('--')]
        sql = ' '.join(lines)

        # Validate: must be UPDATE
        if not sql.upper().startswith("UPDATE"):
            return AgentResponse(
                success=True,
                answer="❌ Failed to generate a valid UPDATE query. Please rephrase your request.",
                confidence=0.3,
                sources=self._make_sources(0.3, "UPDATE SQL generation failed"),
                execution_time_ms=(time.time() - start) * 1000,
            )

        # Safety: must have WHERE clause to prevent updating all rows
        if "WHERE" not in sql.upper():
            return AgentResponse(
                success=True,
                answer=(
                    "❌ Cannot execute UPDATE without a WHERE clause "
                    "(would affect all rows). Please specify which employee to update."
                ),
                confidence=0.8,
                sources=self._make_sources(0.8, "UPDATE rejected: no WHERE clause"),
                execution_time_ms=(time.time() - start) * 1000,
            )

        logger.info(f"Generated UPDATE SQL: {sql}")

        # Step 3: Execute
        result_json = self.tools_handler.execute_custom_mutation(query=sql)
        result_data = json.loads(result_json)

        if result_data.get("status") == "success":
            rows_msg = result_data.get("message", "")

            # Check if any rows were actually affected
            if "0 rows affected" in rows_msg:
                return AgentResponse(
                    success=True,
                    answer=(
                        f"⚠️ **No rows updated** — the WHERE clause didn't match any employee.\n\n"
                        f"**Attempted SQL:**\n```sql\n{sql}\n```\n\n"
                        f"Please verify the employee exists and try again."
                    ),
                    confidence=0.5,
                    sources=self._make_sources(0.5, "UPDATE: 0 rows affected"),
                    execution_time_ms=(time.time() - start) * 1000,
                )

            # Step 4: Verify — show the updated record
            verification = ""
            try:
                if employee_name:
                    verify_json = self.tools_handler.get_employee_record(search_term=employee_name)
                    verify_data = json.loads(verify_json)
                    if verify_data.get("status") == "success":
                        verification = f"\n\n**Updated Record:**\n{verify_data.get('markdown', '')}"
            except Exception:
                pass  # Verification is best-effort

            return AgentResponse(
                success=True,
                answer=f"✅ **Update Successful**\n\n{rows_msg}{verification}",
                confidence=0.92,
                sources=self._make_sources(0.92, f"UPDATE executed: {sql[:100]}"),
                execution_time_ms=(time.time() - start) * 1000,
            )
        else:
            error_msg = result_data.get("error", "Unknown error")
            return AgentResponse(
                success=True,
                answer=(
                    f"❌ **Update Failed**: {error_msg}\n\n"
                    f"**Attempted SQL:**\n```sql\n{sql}\n```"
                ),
                confidence=0.4,
                sources=self._make_sources(0.4, "UPDATE failed"),
                execution_time_ms=(time.time() - start) * 1000,
            )


    def _build_role_instructions(self, user_role: str, db_intent: str) -> str:
        """
        Build concise, intent-specific role instructions for the ReAct system prompt.
        The classify node has already enforced RBAC — these instructions are a
        reminder to the LLM about which tools it may use for the current operation.
        """
        intent_label = db_intent.upper() if db_intent else "SELECT"

        base = {
            "superadmin": (
                f"- You have SUPERADMIN access. You may perform {intent_label} operations.\n"
                "- You can use 'execute_custom_mutation' for INSERT, UPDATE, and DELETE.\n"
                "- You can also use 'execute_custom_select', 'get_employee_record', and 'update_employee_role'."
            ),
            "admin": (
                f"- You have ADMIN access. You may perform {intent_label} operations.\n"
                "- You can use 'execute_custom_mutation' ONLY for UPDATE operations (INSERT and DELETE are blocked).\n"
                "- You can also use 'execute_custom_select', 'get_employee_record', and 'update_employee_role'."
            ),
            "user": (
                "- You have USER access (read-only).\n"
                "- You MUST ONLY use 'get_employee_record' or 'execute_custom_select'.\n"
                "- DO NOT attempt to use 'execute_custom_mutation' or 'update_employee_role'."
            ),
        }
        return base.get(user_role, base["user"])
