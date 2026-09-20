"""
Phase 7: Read-only SQL safety gate.

agent.py generates SQL from a natural-language question, but that text is
LLM output, not trusted code -- it must pass through here before database.py
ever executes it. Nothing here rewrites or "fixes" a query; anything that
isn't clearly a single safe SELECT is rejected outright.
"""

import re

# DuckDB commands beyond the standard DML/DDL set that can mutate state or
# touch the filesystem (extension loading, file export/import, attaching
# other databases, session config) -- all out of bounds for a read-only agent.
FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "ATTACH", "DETACH", "COPY", "PRAGMA", "INSTALL",
    "LOAD", "EXPORT", "IMPORT", "CALL", "SET", "RESET", "VACUUM",
    "CHECKPOINT", "PREPARE", "EXECUTE",
]

_COMMENT_PATTERN = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE
)


def is_safe_select(sql: str) -> tuple[bool, str]:
    """
    Check whether `sql` is a single, read-only SELECT statement.

    Returns (True, cleaned_sql) if safe -- cleaned_sql has comments and a
    trailing semicolon stripped, and is what should actually be executed.
    Returns (False, reason) otherwise.
    """
    if not sql or not sql.strip():
        return False, "Empty query."

    if sql.strip().upper().startswith("NO_SQL"):
        return False, sql.strip()

    # Strip comments first so a forbidden keyword or a stacked statement
    # can't be hidden inside one, and so a harmless keyword mentioned in a
    # comment doesn't cause a false rejection.
    stripped = _COMMENT_PATTERN.sub(" ", sql).strip()
    if not stripped:
        return False, "Query was empty after removing comments."

    # Allow exactly one trailing semicolon; anything else with a semicolon
    # in it is a stacked/multi-statement query and gets rejected outright.
    body = stripped[:-1] if stripped.endswith(";") else stripped
    if ";" in body:
        return False, "Multiple statements are not allowed -- only one SELECT per query."

    if not re.match(r"^\s*(SELECT|WITH)\b", body, re.IGNORECASE):
        return False, "Only SELECT statements (optionally starting with WITH) are allowed."

    match = _KEYWORD_PATTERN.search(body)
    if match:
        return False, f"Query contains a disallowed keyword: {match.group(1).upper()}."

    return True, body.strip()
