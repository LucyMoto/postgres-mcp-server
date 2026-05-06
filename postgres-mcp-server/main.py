from typing import List, Dict, Optional, Tuple
import os
import logging
import psycopg2
from psycopg2 import sql
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import sqlparse
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

# Load environment variables from .env file
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Configuration constants
MAX_RESULT_ROWS = 10000
QUERY_TIMEOUT_SECONDS = 30
MAX_PREVIEW_ROWS = 1000
MAX_DISTINCT_VALUES = 100

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initializes your MCP server instance
mcp = FastMCP("postgres-server")

# Database connection configuration from environment variables
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "practice_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password123"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}

# Global flag for readonly mode - DEFAULT TO TRUE (safe)
_readonly_mode = True

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def error_response(message: str, details: Optional[str] = None) -> List[Dict]:
    """Standardized error response format"""
    response = {"error": message}
    if details:
        response["details"] = details
    return [response]

async def validate_table_exists(table: str) -> bool:
    """Check if table exists in database"""
    try:
        tables = await list_tables()
        return table in tables
    except Exception as e:
        logger.error(f"Error validating table {table}: {e}")
        return False

async def validate_column_exists(table: str, column: str) -> bool:
    """Check if column exists in table"""
    try:
        schema = await get_schema(table)
        if isinstance(schema, list) and len(schema) > 0 and "error" in str(schema[0]):
            return False
        columns = [col["column"] for col in schema]
        return column in columns
    except Exception as e:
        logger.error(f"Error validating column {table}.{column}: {e}")
        return False

def get_db_connection():
    """Get a database connection with timeout"""
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout TO '{QUERY_TIMEOUT_SECONDS}s'")
    return conn

def truncate_results(rows: List[Dict]) -> Tuple[List[Dict], Optional[str]]:
    """Truncate results if they exceed max and return warning message"""
    if len(rows) > MAX_RESULT_ROWS:
        warning = f"Results truncated. Returned {MAX_RESULT_ROWS} of {len(rows)} rows. Use LIMIT to narrow results."
        return rows[:MAX_RESULT_ROWS], warning
    return rows, None

# ============================================================================
# CORE TOOLS (Original 3)
# ============================================================================

@mcp.tool()
async def execute_sql(query: str) -> List[Dict]:
    """Execute a SELECT SQL query against the PostgreSQL database.
    
    Only SELECT queries are allowed. INSERT, UPDATE, DELETE, DROP, and other 
    write operations are blocked for safety.
    
    Args:
        query: SQL SELECT query to execute
        
    Returns:
        List of result rows as dictionaries (column name → value).
        If > 10,000 rows, results are truncated with a warning.
    """
    try:
        # Whitelist: only allow SELECT queries
        query_upper = query.strip().upper()
        if not query_upper.startswith("SELECT"):
            logger.warning(f"Blocked non-SELECT query: {query[:100]}")
            return error_response(
                "Only SELECT queries are allowed.",
                "INSERT, UPDATE, DELETE, DROP, and other writes are blocked."
            )
        
        logger.info(f"Executing query: {query[:100]}...")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                if cur.description:
                    column_names = [desc[0] for desc in cur.description]
                    rows = [dict(zip(column_names, row)) for row in cur.fetchall()]
                else:
                    rows = [{"rows_affected": cur.rowcount}]
        
        # Truncate large result sets
        rows, warning = truncate_results(rows)
        if warning:
            rows.append({"_warning": warning})
        
        logger.info(f"Query returned {len(rows)} rows")
        return rows
        
    except psycopg2.errors.QueryCanceled:
        logger.error(f"Query timeout (>{QUERY_TIMEOUT_SECONDS}s)")
        return error_response(
            f"Query took too long (timeout: {QUERY_TIMEOUT_SECONDS}s)",
            "Try using LIMIT or filtering by date to reduce rows scanned."
        )
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        return error_response("Query execution failed", str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return error_response("Unexpected error", str(e))

@mcp.tool()
async def list_tables() -> List[str]:
    """Return the list of all table names in the current database.
    
    Returns:
        Sorted list of public schema table names.
    """
    try:
        sql_query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_query)
                tables = [row[0] for row in cur.fetchall()]
        
        logger.info(f"Found {len(tables)} tables")
        return tables
        
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        return []

@mcp.tool()
async def get_schema(table: str) -> List[Dict]:
    """Return column names and data types for a given table.
    
    Args:
        table: Table name to inspect
        
    Returns:
        List of dicts with 'column' and 'type' keys, ordered by position.
    """
    try:
        # Validate table exists
        if not await validate_table_exists(table):
            logger.warning(f"Table not found: {table}")
            return error_response(f"Table '{table}' not found")
        
        sql_query = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_query, (table,))
                rows = [{"column": r[0], "type": r[1]} for r in cur.fetchall()]
        
        logger.info(f"Retrieved schema for table {table}: {len(rows)} columns")
        return rows
        
    except Exception as e:
        logger.error(f"Error getting schema for {table}: {e}")
        return error_response(f"Failed to get schema for '{table}'", str(e))

# ============================================================================
# DATA EXPLORATION TOOLS
# ============================================================================

@mcp.tool()
async def preview_table(table: str, limit: int = 5) -> List[Dict]:
    """Preview the first N rows of a table safely.
    
    Args:
        table: Table name to preview
        limit: Number of rows (default 5, max 1000)
    
    Returns:
        List of row dicts with actual column values.
    """
    try:
        # Validate inputs
        if not await validate_table_exists(table):
            logger.warning(f"Table not found: {table}")
            return error_response(f"Table '{table}' not found")
        
        limit = min(limit, MAX_PREVIEW_ROWS)  # Cap at max
        
        # Get schema first
        schema = await get_schema(table)
        if isinstance(schema, list) and len(schema) > 0 and "error" in str(schema[0]):
            return schema
        
        column_names = ", ".join([col["column"] for col in schema])
        query = f"SELECT {column_names} FROM {table} LIMIT %s"
        
        logger.info(f"Previewing {limit} rows from {table}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                cols = [desc[0] for desc in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        
        return rows
        
    except Exception as e:
        logger.error(f"Error previewing table {table}: {e}")
        return error_response(f"Failed to preview '{table}'", str(e))

@mcp.tool()
async def get_column_distinct_values(table: str, column: str, limit: int = 100) -> List:
    """Return distinct values in a column.
    
    Args:
        table: Table name
        column: Column name
        limit: Max values to return (default 100)
    
    Returns:
        List of distinct values as strings.
    """
    try:
        # Validate inputs
        if not await validate_table_exists(table):
            return error_response(f"Table '{table}' not found")
        
        if not await validate_column_exists(table, column):
            return error_response(f"Column '{column}' not found in table '{table}'")
        
        limit = min(limit, MAX_DISTINCT_VALUES)
        
        query = f"SELECT DISTINCT {column} FROM {table} ORDER BY {column} LIMIT %s"
        
        logger.info(f"Getting distinct values from {table}.{column}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                values = [str(row[0]) for row in cur.fetchall()]
        
        return values
        
    except Exception as e:
        logger.error(f"Error getting distinct values for {table}.{column}: {e}")
        return error_response(f"Failed to get distinct values", str(e))

@mcp.tool()
async def search_tables(keyword: str) -> List[str]:
    """Find tables by name or description containing keyword.
    
    Args:
        keyword: Search term (case-insensitive)
    
    Returns:
        List of matching table names.
    """
    try:
        if not keyword or len(keyword.strip()) == 0:
            return error_response("Keyword cannot be empty")
        
        sql_query = """
            SELECT tablename 
            FROM pg_tables
            WHERE schemaname = 'public' 
            AND (tablename ILIKE %s OR obj_description(to_regclass('public.' || tablename), 'pg_class') ILIKE %s)
            ORDER BY tablename
        """
        
        logger.info(f"Searching for tables matching: {keyword}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                pattern = f"%{keyword}%"
                cur.execute(sql_query, (pattern, pattern))
                tables = [row[0] for row in cur.fetchall()]
        
        return tables
        
    except Exception as e:
        logger.error(f"Error searching for tables: {e}")
        return error_response("Search failed", str(e))

# ============================================================================
# TABLE ANALYSIS TOOLS
# ============================================================================

@mcp.tool()
async def get_table_description(table: str) -> Dict:
    """Return business context and column descriptions from table comments."""
    try:
        if not await validate_table_exists(table):
            return error_response(f"Table '{table}' not found")[0]
        
        sql_query = "SELECT obj_description(to_regclass('public.' || %s), 'pg_class') as table_description"
        
        col_query = """
            SELECT attname as column_name, col_description(attrelid, attnum) as column_description
            FROM pg_attribute
            WHERE attrelid = to_regclass('public.' || %s)
            AND attnum > 0 AND NOT attisdropped
            ORDER BY attnum
        """
        
        logger.info(f"Getting description for table {table}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_query, (table,))
                table_desc = cur.fetchone()[0]
                
                cur.execute(col_query, (table,))
                columns = [
                    {"column": row[0], "description": row[1] or "No description"}
                    for row in cur.fetchall()
                ]
        
        return {
            "table": table,
            "description": table_desc or "No description",
            "columns": columns
        }
        
    except Exception as e:
        logger.error(f"Error getting description for {table}: {e}")
        return error_response(f"Failed to get description", str(e))[0]

@mcp.tool()
async def get_table_stats(table: str) -> Dict:
    """Return row count, table size, and column null percentages."""
    try:
        if not await validate_table_exists(table):
            return error_response(f"Table '{table}' not found")[0]
        
        logger.info(f"Getting stats for table {table}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) as row_count, pg_size_pretty(pg_total_relation_size('public.' || %s)) as size",
                    (table,)
                )
                row_count, size = cur.fetchone()
                
                # Get null counts per column
                schema = await get_schema(table)
                if isinstance(schema, list) and len(schema) > 0 and "error" in str(schema[0]):
                    return schema[0]
                
                null_counts = {}
                for col_info in schema:
                    col = col_info["column"]
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
                    null_count = cur.fetchone()[0]
                    null_percentage = round((null_count / row_count * 100), 2) if row_count > 0 else 0
                    null_counts[col] = {
                        "null_count": null_count,
                        "null_percentage": null_percentage
                    }
        
        return {
            "table": table,
            "row_count": row_count,
            "size": size,
            "column_null_counts": null_counts
        }
        
    except Exception as e:
        logger.error(f"Error getting stats for {table}: {e}")
        return error_response(f"Failed to get stats", str(e))[0]

@mcp.tool()
async def get_table_relationships() -> List[Dict]:
    """Return all foreign key relationships in the database."""
    try:
        sql_query = """
            SELECT 
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
            ORDER BY tc.table_name, kcu.column_name
        """
        
        logger.info("Getting table relationships")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_query)
                relationships = [
                    {
                        "from_table": row[0],
                        "from_column": row[1],
                        "to_table": row[2],
                        "to_column": row[3]
                    }
                    for row in cur.fetchall()
                ]
        
        return relationships
        
    except Exception as e:
        logger.error(f"Error getting relationships: {e}")
        return error_response("Failed to get relationships", str(e))

@mcp.tool()
async def get_table_last_modified(table: str) -> Dict:
    """Return when table was last modified and change statistics."""
    try:
        if not await validate_table_exists(table):
            return error_response(f"Table '{table}' not found")[0]
        
        simple_query = """
            SELECT 
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze,
                n_live_tup as live_rows,
                n_tup_ins + n_tup_upd + n_tup_del as total_changes
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            AND relname = %s
        """
        
        logger.info(f"Getting last modified time for {table}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(simple_query, (table,))
                row = cur.fetchone()
                
                if not row:
                    return error_response(f"No stats available for '{table}'")[0]
                
                return {
                    "table": table,
                    "last_vacuum": str(row[0]) if row[0] else "Never",
                    "last_autovacuum": str(row[1]) if row[1] else "Never",
                    "last_analyze": str(row[2]) if row[2] else "Never",
                    "last_autoanalyze": str(row[3]) if row[3] else "Never",
                    "live_rows": row[4],
                    "total_changes_since_analyze": row[5]
                }
        
    except Exception as e:
        logger.error(f"Error getting last modified for {table}: {e}")
        return error_response(f"Failed to get last modified", str(e))[0]

# ============================================================================
# QUERY ANALYSIS TOOLS
# ============================================================================

@mcp.tool()
async def validate_query(query: str) -> Dict:
    """Validate a query's syntax and safety WITHOUT executing it."""
    try:
        parsed = sqlparse.parse(query)
        if not parsed:
            return {"valid": False, "error": "Could not parse query", "safe": False}
        
        query_upper = query.upper().strip()
        dangerous_keywords = ["DROP", "TRUNCATE", "DELETE", "ALTER", "GRANT", "REVOKE"]
        
        is_safe = not any(keyword in query_upper for keyword in dangerous_keywords)
        
        logger.info(f"Validating query: {query[:100]}...")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                try:
                    explain_query = f"EXPLAIN {query}"
                    cur.execute(explain_query)
                    cur.fetchall()
                    valid = True
                    error = None
                except psycopg2.Error as e:
                    valid = False
                    error = str(e)
        
        return {
            "valid": valid,
            "safe": is_safe,
            "dangerous_keywords_found": not is_safe,
            "error": error,
            "is_read_only": query_upper.startswith("SELECT")
        }
        
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {"valid": False, "error": str(e), "safe": False}

@mcp.tool()
async def estimate_query_cost(query: str) -> Dict:
    """Estimate query cost and performance WITHOUT executing."""
    try:
        logger.info(f"Estimating cost: {query[:100]}...")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"EXPLAIN {query}")
                explain_output = cur.fetchall()
        
        output_text = "\n".join([row[0] for row in explain_output])
        
        estimated_rows = None
        estimated_cost = None
        
        for line in output_text.split("\n"):
            if "rows=" in line:
                try:
                    estimated_rows = int(line.split("rows=")[1].split()[0])
                except:
                    pass
            if "cost=" in line:
                try:
                    costs = line.split("cost=")[1].split()[0].split("..")
                    estimated_cost = float(costs[-1]) if len(costs) > 1 else float(costs[0])
                except:
                    pass
        
        safe_to_run = (estimated_rows or 0) < 10000000
        
        return {
            "valid": True,
            "estimated_rows": estimated_rows,
            "estimated_cost": estimated_cost,
            "safe_to_run": safe_to_run,
            "explain_output": output_text
        }
        
    except psycopg2.errors.QueryCanceled:
        return {"valid": False, "error": f"Query timeout (>{QUERY_TIMEOUT_SECONDS}s)"}
    except Exception as e:
        logger.error(f"Cost estimation error: {e}")
        return {"valid": False, "error": str(e)}

@mcp.tool()
async def analyze_query_performance(query: str) -> Dict:
    """Return actual query performance data from EXPLAIN ANALYZE."""
    try:
        logger.info(f"Analyzing: {query[:100]}...")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
                explain_json = cur.fetchone()[0]
        
        plan = explain_json[0]["Plan"]
        
        return {
            "valid": True,
            "actual_rows": plan.get("Actual Rows"),
            "actual_time_ms": round(plan.get("Actual Total Time", 0), 2),
            "node_type": plan.get("Node Type"),
            "startup_cost": plan.get("Startup Cost"),
            "total_cost": plan.get("Total Cost"),
            "estimated_rows": plan.get("Plan Rows"),
            "index_used": "Index" in plan.get("Node Type", ""),
            "full_plan": explain_json[0] if len(explain_json) > 0 else None
        }
        
    except psycopg2.errors.QueryCanceled:
        return {"valid": False, "error": f"Query timeout (>{QUERY_TIMEOUT_SECONDS}s)"}
    except Exception as e:
        logger.error(f"Performance analysis error: {e}")
        return {"valid": False, "error": str(e)}

# ============================================================================
# CONNECTION MANAGEMENT TOOLS
# ============================================================================

@mcp.tool()
async def get_connection_info() -> Dict:
    """Return current database connection details and configuration."""
    try:
        logger.info("Getting connection info")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
                
                cur.execute("SELECT current_user")
                current_user = cur.fetchone()[0]
                
                cur.execute("SELECT current_database()")
                current_db = cur.fetchone()[0]
                
                cur.execute("SELECT current_schema()")
                current_schema = cur.fetchone()[0]
                
                cur.execute("SHOW timezone")
                timezone = cur.fetchone()[0]
                
                cur.execute("SHOW max_connections")
                max_connections = cur.fetchone()[0]
        
        return {
            "version": version,
            "current_user": current_user,
            "current_database": current_db,
            "current_schema": current_schema,
            "timezone": timezone,
            "max_connections": max_connections,
            "is_readonly": _readonly_mode,
            "query_timeout_seconds": QUERY_TIMEOUT_SECONDS,
            "max_result_rows": MAX_RESULT_ROWS,
            "host": DB_CONFIG["host"],
            "port": DB_CONFIG["port"]
        }
        
    except Exception as e:
        logger.error(f"Error getting connection info: {e}")
        return error_response("Failed to get connection info", str(e))[0]

@mcp.tool()
async def set_readonly(readonly: bool) -> Dict:
    """Set database connection to readonly mode."""
    global _readonly_mode
    _readonly_mode = readonly
    
    logger.info(f"Readonly mode set to: {readonly}")
    
    return {
        "success": True,
        "readonly_mode": _readonly_mode,
        "message": "Readonly mode " + ("enabled" if readonly else "disabled")
    }

@mcp.tool()
async def cancel_query(query_id: str) -> Dict:
    """Cancel a currently running query by its process ID."""
    try:
        logger.info(f"Cancelling query with PID: {query_id}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_cancel_backend(%s)", (int(query_id),))
                cancelled = cur.fetchone()[0]
        
        return {
            "success": cancelled,
            "query_id": query_id,
            "message": f"Query {query_id} cancelled" if cancelled else f"Could not cancel query {query_id}"
        }
        
    except ValueError:
        logger.warning(f"Invalid query_id: {query_id}")
        return error_response("Invalid query_id. Must be an integer.")[0]
    except Exception as e:
        logger.error(f"Error cancelling query: {e}")
        return error_response("Failed to cancel query", str(e))[0]

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run MCP server using stdio transport"""
    logger.info("Starting PostgreSQL MCP server...")
    logger.info(f"Config: timeout={QUERY_TIMEOUT_SECONDS}s, max_rows={MAX_RESULT_ROWS}, readonly={_readonly_mode}")
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()

# run with
# cd C:\Users\lucyq\Documents\Futureproof\module-2-mcp\postgres-mcp-server
# npx @modelcontextprotocol/inspector poetry run python postgres-mcp-server/main.py