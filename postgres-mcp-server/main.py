from typing import List, Dict, Optional
import os
import psycopg2
from psycopg2 import sql
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import sqlparse

# Load environment variables from .env file
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Initializes your MCP server instance. It's used to register your tools.
mcp = FastMCP("postgres-server")

# Database connection configuration from environment variables
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "practice_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password123"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}

@mcp.tool()
async def execute_sql(query: str) -> List[Dict]:
    """Execute a SELECT SQL query against the PostgreSQL database and return rows as a list of dictionaries (column name → value)"""
    #Whitelist: only allow SELECT (and never INSERT/UPDATE/DELETE)
    query_upper = query.strip().upper()
    if not query_upper.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed. Never INSERT, UPDATE or DELETE")
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            column_names = [desc[0] for desc in cur.description]
            rows = [dict(zip(column_names, row)) for row in cur.fetchall()]
    return rows

@mcp.tool()
async def list_tables() -> List[str]:
    """Return the list of table names available in the current database"""
    sql = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
        """
    
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = [row[0] for row in cur.fetchall()]
    return rows

@mcp.tool()
async def get_schema(table: str) -> List[Dict]:
    """Return column names and types for a given table."""
    sql = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (table,))
            rows = [{"column": r[0], "type": r[1]} for r in cur.fetchall()]
    return rows

# ============================
# DATA EXPLORATION TOOLS
# ============================

@mcp.tool()
async def preview_table(table: str, limit: int = 5) -> List[Dict]:
    """Preview the first n rows of a table safely without SELECT *"""
    # Get column names first
    schema = await get_schema(table)
    if not schema:
        return []

    column_names = ", ".join([col["column"] for col in schema])
    query = f"SELECT {column_names} FROM {table} LIMIT %s"

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return rows
    
@mcp.tool()
async def get_column_distinct_values(table: str, column: str, limit: int = 100) -> List[str]:
    """Return distinct values in a column (useful for understanding enums/categories)"""
    query = f"SELECT DISTINCT {column} FROM {table} ORDER BY {column} LIMIT %s"
    
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            values = [str(row[0]) for row in cur.fetchall()]
    return values

@mcp.tool()
async def search_tables(keyword: str) -> List[str]:
    """Find tables by name or description containing keyword"""
    sql_query = """
        SELECT tablename 
        FROM pg_tables
        WHERE schemaname = 'public' 
        AND (tablename ILIKE %s OR obj_description(to_regclass('public.' || tablename), 'pg_class') ILIKE %s)
        ORDER BY tablename
    """
    
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            pattern = f"%{keyword}%"
            cur.execute(sql_query, (pattern, pattern))
            tables = [row[0] for row in cur.fetchall()]
    return tables

# ========================
# TABLE ANALYSIS TOOLS
# ========================
@mcp.tool()
async def get_table_description(table: str) -> Dict:
    """Return business context and column descriptions from table comments"""
    sql_query = """
        SELECT 
            obj_description(to_regclass('public.' || %s), 'pg_class') as table_description
    """
    
    # Get column descriptions
    col_query = """
        SELECT 
            attname as column_name,
            col_description(attrelid, attnum) as column_description
        FROM pg_attribute
        WHERE attrelid = to_regclass('public.' || %s)
        AND attnum > 0
        AND NOT attisdropped
        ORDER BY attnum
    """
    
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            # Get table description
            cur.execute(sql_query, (table,))
            table_desc = cur.fetchone()[0]
            
            # Get column descriptions
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

@mcp.tool()
async def get_table_stats(table: str) -> Dict:
    """Return row count, table size, and column null counts"""
    sql_query = """
        SELECT 
            (SELECT COUNT(*) FROM {table}) as row_count,
            pg_size_pretty(pg_total_relation_size('public.' || %s)) as size
    """
    
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            # Get row count and size
            cur.execute(sql_query.format(table=table), (table,))
            row_count, size = cur.fetchone()
            
            # Get null counts per column
            schema = await get_schema(table)
            null_counts = {}
            for col_info in schema:
                col = col_info["column"]
                null_query = f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"
                cur.execute(null_query)
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







    
def main():
    # Run MCP server using stdio transport for AI assistant integration
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()

# run with
# cd C:\Users\lucyq\Documents\Futureproof\module-2-mcp\postgres-mcp-server
# npx @modelcontextprotocol/inspector poetry run python postgres-mcp-server/main.py