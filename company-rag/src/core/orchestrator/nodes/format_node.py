"""
Format node — Final formatting of the response.
Cleans up raw synthesized answers:
  1. Sanitizes raw JSON that leaked from tool outputs
  2. Normalizes PDF download links to proper markdown syntax
  3. Ensures markdown tables are well-formed (blank lines before/after)
  4. Removes excessive whitespace
"""

import re
import json
from src.core.orchestrator.state import OmniQueryState
from src.utils.logger import setup_logger

logger = setup_logger("FormatNode")

# Signals that indicate the JSON is a DB tool error/empty result (not data)
_JSON_NO_DATA_MESSAGES = [
    "no matching employees",
    "no matching",
    "not found",
    "failed",
    "does not exist",
    "no data",
    "no results",
    "0 rows",
]


def _sanitize_raw_json(text: str) -> str:
    """
    Detect and convert raw JSON tool outputs into human-readable text.

    Handles cases where the ReAct loop leaks tool result JSON directly
    into the final answer, e.g.:
      {"status": "success", "message": "No matching employees found..."}
    
    Strategy:
      - If the entire response is a JSON object/array, parse and extract
        the most useful field ("message", "answer", "error", "result").
      - If it's a "no data" type message, convert to a friendly string.
      - If parsing fails, leave the original text unchanged.
    """
    stripped = text.strip()

    # Only process strings that look entirely like JSON objects/arrays
    if not (
        (stripped.startswith("{") and stripped.endswith("}"))
        or (stripped.startswith("[") and stripped.endswith("]"))
    ):
        return text

    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return text  # Not valid JSON — leave as-is

    if isinstance(data, list):
        # Unlikely to be a raw list, but handle gracefully
        return text

    if isinstance(data, dict):
        # Priority order: extract the most useful field
        for key in ("answer", "result", "message", "error", "detail"):
            if key in data:
                value = str(data[key]).strip()
                if not value:
                    continue

                # Check if it's a "no data" type message → friendly output
                value_lower = value.lower()
                if any(sig in value_lower for sig in _JSON_NO_DATA_MESSAGES):
                    logger.info("FormatNode: Converted raw JSON no-data response to friendly message.")
                    return "I couldn't find any matching data for your request. Please try rephrasing or provide more details."

                logger.info(f"FormatNode: Extracted '{key}' field from raw JSON response.")
                return value

        # JSON has none of the expected keys — return a generic message
        status = data.get("status", "")
        if status == "success":
            return "The operation completed successfully."
        return "I couldn't process the response correctly. Please try again."

    return text


def format_node(state: OmniQueryState) -> dict:
    """Format the final response with proper markdown structure"""
    answer = state.get("synthesized_answer", "No answer available.")

    if not answer or not answer.strip():
        return {"formatted_response": "No answer available."}

    formatted = answer

    # ── 1. Sanitize raw JSON leakage from tool outputs ──
    formatted = _sanitize_raw_json(formatted)

    # ── 2. Normalize PDF download links ──
    # Catch raw URLs like /static/reports/xxx.pdf and wrap in markdown link syntax
    formatted = re.sub(
        r'(?<!\[)(?<!\()(/static/reports/[\w\-]+\.pdf)(?!\))',
        r'[📥 Download PDF Report](\1)',
        formatted,
    )

    # Ensure existing markdown links to reports have the download emoji
    formatted = re.sub(
        r'\[([^\]]*?)\]\((/static/reports/[\w\-]+\.pdf)\)',
        r'[📥 \1](\2)',
        formatted,
    )
    # Clean up double emojis if already had one
    formatted = formatted.replace("📥 📥", "📥")

    # ── 3. Clean up table formatting ──
    # Ensure there's a blank line before and after markdown tables
    lines = formatted.split("\n")
    cleaned_lines = []
    in_table = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")
        is_separator = bool(re.match(r'^\|[\s\-:|]+\|$', stripped))

        if is_table_line or is_separator:
            if not in_table:
                if cleaned_lines and cleaned_lines[-1].strip() != "":
                    cleaned_lines.append("")
                in_table = True
            cleaned_lines.append(line)
        else:
            if in_table:
                if stripped != "":
                    cleaned_lines.append("")
                in_table = False
            cleaned_lines.append(line)

    formatted = "\n".join(cleaned_lines)

    # ── 4. Clean up excessive whitespace ──
    formatted = re.sub(r'\n{3,}', '\n\n', formatted)
    formatted = formatted.strip()

    logger.info(f"FormatNode: formatted response ({len(formatted)} chars)")

    return {
        "formatted_response": formatted,
    }
