# PostgreSQL MCP Server

An MCP server that exposes PostgreSQL database operations as tools for AI assistants.

## What is MCP?

Model Context Protocol (MCP) connects AI assistants to external tools and data. This server lets AI assistants execute SQL queries, inspect your PostgreSQL database schema, and validate query performance—all with built-in safety guardrails.

## Setup

**Python version:** This project requires Python 3.10–3.13. Python 3.14 is excluded due to upstream dependency wheel support (e.g., `psycopg2-binary` and `pydantic-core`).

### 1. Install Dependencies

> **Note:** This project uses Poetry for dependency management. If you don't have Poetry installed:
> ```bash
> curl -sSL https://install.python-poetry.org | python3 -
> ```
> See the [official Poetry documentation](https://python-poetry.org/docs/#installation) for alternative installation methods.

```bash
poetry install
```

### 2. Configure Database

Copy `.env.example` to `.env` and add your PostgreSQL credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```
DB_NAME=your_database
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

## Testing

### Quick Test (Recommended)

```bash
cd postgres-mcp-server
poetry run python test_tools.py
```

This tests all 16 tools in ~10 seconds and exits. Look for:
```
✓ ALL TESTS PASSED!
```

### MCP Inspector (Browser UI)

> **Note:** Requires Node.js (npm). Get it from [nodejs.org](https://nodejs.org).

```bash
npx @modelcontextprotocol/inspector poetry run python postgres-mcp-server/main.py
```

Opens a web UI where you can manually test individual tools.

### Manual Testing

```bash
poetry run python postgres-mcp-server/main.py
```

Press `Ctrl+C` to stop. No errors = working correctly.

## Available Tools (16 Total)

### Core Tools (3)
- **`list_tables()`** — List all table names in the database
- **`get_schema(table)`** — Get column names and types for a table
- **`execute_sql(query)`** — Execute a SELECT query (writes blocked by default)

### Data Exploration (3)
- **`preview_table(table, limit=5)`** — Preview first N rows safely
- **`get_column_distinct_values(table, column)`** — See unique values in a column
- **`search_tables(keyword)`** — Find tables by name or description

### Table Analysis (5)
- **`get_table_description(table)`** — Get business context from table comments
- **`get_table_stats(table)`** — Get row count, size, and null percentages per column
- **`get_table_relationships()`** — Get all foreign key constraints
- **`get_table_last_modified(table)`** — When table was last updated
- **`get_column_distinct_values(table, column)`** — Unique values in a column (useful for enums/categories)

### Query Analysis (3)
- **`validate_query(query)`** — Check syntax and safety WITHOUT executing
- **`estimate_query_cost(query)`** — Estimate performance before running
- **`analyze_query_performance(query)`** — Actual performance metrics (executes query)

### Connection Management (3)
- **`get_connection_info()`** — Database version, user, timezone, settings
- **`set_readonly(readonly)`** — Toggle readonly mode (write protection)
- **`cancel_query(query_id)`** — Kill a runaway query by PID

## Safety Features

✅ **SELECT-only by default** — Writes blocked automatically  
✅ **Query timeouts** — Runaway queries killed after 30 seconds  
✅ **Result limits** — Large queries capped at 10,000 rows (with warning)  
✅ **Input validation** — Table/column names checked before execution  
✅ **Structured errors** — Consistent error format across all tools  
✅ **Full logging** — Audit trail of all operations  

## Connect to Cursor

Add to your Cursor MCP config (global settings):

```json
{
  "mcpServers": {
    "postgres": {
      "command": "poetry",
      "args": ["-C", "/absolute/path/to/postgres-mcp-server", "run", "python", "postgres-mcp-server/main.py"]
    }
  }
}
```

Replace `/absolute/path/to/postgres-mcp-server` with your actual project path.

## Configuration

Edit constants in `postgres-mcp-server/main.py`:

```python
MAX_RESULT_ROWS = 10000        # Cap on query results
QUERY_TIMEOUT_SECONDS = 30     # Query timeout
MAX_PREVIEW_ROWS = 1000        # Max rows for preview_table
MAX_DISTINCT_VALUES = 100      # Max distinct values returned
```

## Architecture

```
postgres-mcp-server/
├── main.py                    # All 16 tools + helper functions
├── test_tools.py              # Quick validation script
├── .env                       # Database credentials
└── pyproject.toml             # Dependencies (Poetry)
```

### Key Components

- **FastMCP** — Lightweight MCP server framework
- **psycopg2** — PostgreSQL driver
- **sqlparse** — SQL syntax validation
- **Python logging** — Operation audit trail

---

*Future Proof Data Science — Teaching data scientists to build AI systems that work with real databases.*
