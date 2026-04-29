import json
from dataclasses import dataclass
from typing import Dict, Any, List
from sqlalchemy import text
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class DBAgentTools:
    """Contains semantic tools for interacting with the database securely."""
    
    def __init__(self, engine):
        self.engine = engine

    def _format_markdown_table(self, rows: List[Dict], title: str = "Query Results") -> str:
        """Formats an array of dicts into a strict Markdown table layout."""
        if not rows:
            return "No data found."
            
        headers = list(rows[0].keys())
        header_row = "| " + " | ".join(str(h).replace("_", " ").title() for h in headers) + " |"
        separator = "| " + " | ".join("---" for _ in headers) + " |"
        
        data_rows = []
        for row in rows:
            cells = []
            for h in headers:
                val = str(row.get(h, ""))
                val = val.replace("|", "/") # Prevent table corruption
                cells.append(val)
            data_rows.append("| " + " | ".join(cells) + " |")
            
        return f"**{title}** ({len(rows)} records)\n\n{header_row}\n{separator}\n" + "\n".join(data_rows)

    def get_employee_record(self, email: str = None, first_name: str = None, last_name: str = None, search_term: str = None, **kwargs) -> str:
        if kwargs.get('query'):
            return json.dumps({"error": "You mistakenly passed a 'query' argument. ONLY the 'execute_custom_select' tool takes a 'query' argument! Please use 'execute_custom_select' if you want to run SQL."})
        """Retrieves an employee record based on explicit criteria or a general search term."""
        conditions = []
        params = {}
        
        if search_term:
            conditions.append("(first_name ILIKE :search_term OR last_name ILIKE :search_term OR email ILIKE :search_term OR CONCAT(first_name, ' ', last_name) ILIKE :search_term)")
            params['search_term'] = f"%{search_term}%"
        if email:
            conditions.append("email = :email")
            params['email'] = email
        if first_name:
            conditions.append("first_name ILIKE :first_name")
            params['first_name'] = f"%{first_name}%"
        if last_name:
            conditions.append("last_name ILIKE :last_name")
            params['last_name'] = f"%{last_name}%"
            
        if not conditions:
            return json.dumps({"error": "You must provide at least one of email, first_name, last_name, or search_term to search."})
            
        where_clause = " AND ".join(conditions)
        query = text(f"SELECT id, first_name, last_name, email, job_title, department_id, role, salary FROM employees WHERE {where_clause} LIMIT 5")
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query, params)
                rows = [dict(row._mapping) for row in result]
                
                # Convert decimal to str
                for r in rows:
                    if 'salary' in r:
                        r['salary'] = str(r['salary'])

                if not rows:
                    return json.dumps({"status": "failed", "message": "No matching employees found for the provided criteria."})
                
                md_table = self._format_markdown_table(rows, "Employee Record(s)")
                return json.dumps({
                    "status": "success", 
                    "message": f"Data securely fetched. Provide exactly the following Markdown table in your Final Answer:\n\n{md_table}",
                    "markdown": md_table
                })
        except Exception as e:
            logger.error(f"Error in get_employee_record tool: {e}")
            return json.dumps({"error": f"Database query failed: {str(e)}"})

    def update_employee_role(self, email: str = None, new_role: str = None, **kwargs) -> str:
        """Updates the role of a specified employee. Bypasses naive DELETE/INSERT LLM logic."""
        if kwargs.get('query'):
            return json.dumps({"error": "You mistakenly passed a 'query' argument. If you want to run SQL, use 'execute_custom_select'."})
        
        if not email or not new_role:
            return json.dumps({"error": "email and new_role are required parameters."})
            
        allowed_roles = ["user", "admin", "superadmin"]
        if new_role.lower() not in allowed_roles:
            return json.dumps({"error": f"Invalid role '{new_role}'. Allowed roles are {allowed_roles}."})
            
        try:
            with self.engine.begin() as conn:  # using begin() for auto-commit transaction
                # Verify employee exists first to avoid silent failures
                verify_query = text("SELECT id, role FROM employees WHERE email = :email")
                res = conn.execute(verify_query, {"email": email}).fetchone()
                
                if not res:
                    return json.dumps({"error": f"Employee with email '{email}' does not exist."})
                    
                if res._mapping['role'] == new_role:
                    return json.dumps({"message": f"Employee '{email}' already has the role '{new_role}'."})
                
                update_query = text("UPDATE employees SET role = :role WHERE email = :email")
                result = conn.execute(update_query, {"role": new_role, "email": email})
                
                if result.rowcount > 0:
                    return json.dumps({"status": "success", "message": f"Role updated to '{new_role}' for '{email}'."})
                else:
                    return json.dumps({"error": "Update failed unexpectedly."})
        except Exception as e:
            logger.error(f"Error in update_employee_role tool: {e}")
            return json.dumps({"error": f"Database operation failed: {str(e)}"})

    def execute_custom_select(self, query: str = None, export_pdf: bool = False, **kwargs) -> str:
        """Executes a custom SELECT query ONLY. Useful for aggregations."""
        if not query:
            return json.dumps({"error": "You must provide a 'query' string containing the SQL statement. Example: {'query': 'SELECT * FROM employees', 'export_pdf': true}"})
            
        if not query.strip().upper().startswith("SELECT"):
            return json.dumps({"error": "Only SELECT queries are allowed via this tool."})
            
        if "UPDATE" in query.upper() or "DELETE" in query.upper() or "INSERT" in query.upper() or "DROP" in query.upper():
            return json.dumps({"error": "Data mutation keywords detected. Use specific semantic tools to modify data."})
            
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                rows = [dict(row._mapping) for row in result]
                
                for r in rows:
                    for k, v in r.items():
                        if not isinstance(v, (int, float, str, bool, type(None))):
                            r[k] = str(v)
                            
                if export_pdf and len(rows) > 0:
                    try:
                        from fpdf import FPDF
                        import os
                        import uuid
                        
                        pdf = FPDF()
                        pdf.add_page(orientation="L") # Landscape for tables
                        pdf.set_font("helvetica", size=10)
                        
                        # Add simple header
                        pdf.set_font("helvetica", style="B", size=14)
                        pdf.cell(0, 10, text="Database Query Results", align='C')
                        pdf.ln(15)
                        
                        # Headers
                        headers = list(rows[0].keys())
                        col_width = 270 / max(len(headers), 1)
                        
                        pdf.set_font("helvetica", style="B", size=10)
                        for header in headers:
                            pdf.cell(col_width, 10, text=str(header)[:20], border=1)
                        pdf.ln()
                        
                        pdf.set_font("helvetica", size=9)
                        for row in rows:
                            for header in headers:
                                pdf.cell(col_width, 10, text=str(row.get(header, ""))[:20], border=1)
                            pdf.ln()
                            
                        # Save file
                        reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "web", "static", "reports")
                        os.makedirs(reports_dir, exist_ok=True)
                        filename = f"report_{uuid.uuid4().hex[:8]}.pdf"
                        file_path = os.path.join(reports_dir, filename)
                        pdf.output(file_path)
                        
                        return json.dumps({
                            "status": "success", 
                            "row_count": len(rows), 
                            "message": f"Data too large to display. PDF successfully generated. Tell the user to download it from: [Download Report](/static/reports/{filename})",
                            "pdf_url": f"/static/reports/{filename}"
                        })
                    except Exception as pdf_e:
                        logger.error(f"Failed to generate PDF: {pdf_e}")
                        pass
                
                md_table = self._format_markdown_table(rows[:50], "Query Results")
                return json.dumps({
                    "status": "success", 
                    "row_count": len(rows), 
                    "message": f"Retrieved {len(rows)} rows. Provide exactly the following Markdown table in your Final Answer:\n\n{md_table}",
                    "markdown": md_table
                })
        except Exception as e:
            return json.dumps({"error": f"Invalid SQL or constraint violation: {str(e)}"})

    def execute_custom_mutation(self, query: str = None, **kwargs) -> str:
        """Executes a custom database mutation (INSERT, UPDATE, DELETE)."""
        if not query:
            return json.dumps({"error": "You must provide a 'query' string."})
            
        role = getattr(self, "current_role", "user")
        
        query_upper = query.strip().upper()
        if query_upper.startswith("SELECT"):
            return json.dumps({"error": "Use execute_custom_select for SELECT queries."})
            
        is_insert = "INSERT" in query_upper
        is_delete = "DELETE" in query_upper
        is_update = "UPDATE" in query_upper
        
        if role == "user":
            return json.dumps({"error": "PERMISSION DENIED: Users cannot perform database mutations."})
        elif role == "admin":
            if is_delete or is_insert:
                return json.dumps({"error": f"PERMISSION DENIED: Admins cannot perform {'DELETE' if is_delete else 'INSERT'} operations. Only UPDATE is allowed."})
            if not is_update:
                return json.dumps({"error": "Admins can only perform UPDATE operations."})
        elif role == "superadmin":
            pass # All allowed
        else:
            return json.dumps({"error": "Unknown role."})
            
        try:
            # We use begin() instead of connect() for an auto-commit transaction
            with self.engine.begin() as conn:
                result = conn.execute(text(query))
                rowcount = result.rowcount
            return json.dumps({"status": "success", "message": f"Mutation executed successfully. {rowcount} rows affected."})
        except Exception as e:
            logger.error(f"Error in execute_custom_mutation: {e}")
            return json.dumps({"error": f"Database operation failed: {str(e)}"})
