#!/usr/bin/env python3
"""
Quick test script for PostgreSQL MCP tools.
Run this instead of using the browser MCP Inspector for faster iteration.

Usage:
    cd postgres-mcp-server
    poetry run python test_tools.py
"""

import asyncio
import sys
from pathlib import Path

# Add the inner postgres-mcp-server directory to path
sys.path.insert(0, str(Path(__file__).parent / "postgres-mcp-server"))

# Import the tools
from main import (
    execute_sql,
    list_tables,
    get_schema,
    preview_table,
    get_column_distinct_values,
    search_tables,
    get_table_description,
    get_table_stats,
    get_table_relationships,
    get_table_last_modified,
    validate_query,
    estimate_query_cost,
    analyze_query_performance,
    get_connection_info,
    set_readonly,
    cancel_query,
)

async def test_all():
    """Run all tools in sequence"""
    print("=" * 80)
    print("TESTING ALL MCP TOOLS")
    print("=" * 80)
    
    # Test 1: Connection
    print("\n✓ TEST 1: get_connection_info")
    try:
        result = await get_connection_info()
        print(f"  Database: {result.get('current_database')}")
        print(f"  User: {result.get('current_user')}")
        print(f"  Readonly mode: {result.get('is_readonly')}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 2: List tables
    print("\n✓ TEST 2: list_tables")
    try:
        tables = await list_tables()
        print(f"  Found {len(tables)} tables: {tables}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    if not tables:
        print("  ✗ No tables found!")
        return False
    
    test_table = tables[0]  # Use first table
    print(f"  Using table: {test_table}")
    
    # Test 3: Get schema
    print(f"\n✓ TEST 3: get_schema('{test_table}')")
    try:
        schema = await get_schema(test_table)
        if isinstance(schema, list) and len(schema) > 0 and "error" in str(schema[0]):
            print(f"  ✗ ERROR: {schema}")
            return False
        print(f"  Columns: {len(schema)}")
        for col in schema[:3]:
            print(f"    - {col['column']}: {col['type']}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 4: Preview table
    print(f"\n✓ TEST 4: preview_table('{test_table}', limit=3)")
    try:
        rows = await preview_table(test_table, limit=3)
        if isinstance(rows, list) and len(rows) > 0 and "error" in str(rows[0]):
            print(f"  ✗ ERROR: {rows}")
            return False
        print(f"  Got {len(rows)} rows")
        if rows and "_warning" not in str(rows[0]):
            print(f"  Sample row keys: {list(rows[0].keys())[:3]}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 5: Get table stats
    print(f"\n✓ TEST 5: get_table_stats('{test_table}')")
    try:
        stats = await get_table_stats(test_table)
        if isinstance(stats, dict) and "error" in stats:
            print(f"  ✗ ERROR: {stats}")
            return False
        print(f"  Row count: {stats.get('row_count')}")
        print(f"  Size: {stats.get('size')}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 6: Get table description
    print(f"\n✓ TEST 6: get_table_description('{test_table}')")
    try:
        desc = await get_table_description(test_table)
        if isinstance(desc, dict) and "error" in desc:
            print(f"  ✗ ERROR: {desc}")
            return False
        print(f"  Description: {desc.get('description', 'None')}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 7: Get table last modified
    print(f"\n✓ TEST 7: get_table_last_modified('{test_table}')")
    try:
        last_mod = await get_table_last_modified(test_table)
        if isinstance(last_mod, dict) and "error" in last_mod:
            print(f"  ✗ ERROR: {last_mod}")
            return False
        print(f"  Live rows: {last_mod.get('live_rows')}")
        print(f"  Last analyze: {last_mod.get('last_analyze')}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 8: Get table relationships
    print("\n✓ TEST 8: get_table_relationships()")
    try:
        rels = await get_table_relationships()
        print(f"  Found {len(rels)} foreign key relationships")
        if rels:
            print(f"    Example: {rels[0]['from_table']}.{rels[0]['from_column']} → {rels[0]['to_table']}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 9: Get column distinct values
    print(f"\n✓ TEST 9: get_column_distinct_values('{test_table}')")
    try:
        schema = await get_schema(test_table)
        if schema and len(schema) > 0:
            col = schema[0]["column"]
            values = await get_column_distinct_values(test_table, col, limit=5)
            if isinstance(values, list) and len(values) > 0 and "error" in str(values[0]):
                print(f"  ✗ ERROR: {values}")
                return False
            print(f"  Distinct values in '{col}': {len(values)}")
            print(f"    Sample: {values[:3]}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 10: Search tables
    print("\n✓ TEST 10: search_tables('user')")
    try:
        found = await search_tables("user")
        print(f"  Found {len(found)} tables matching 'user'")
        if found:
            print(f"    Tables: {found}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 11: Validate query
    print("\n✓ TEST 11: validate_query(SELECT ...)")
    try:
        result = await validate_query(f"SELECT * FROM {test_table} LIMIT 5")
        if not result.get("valid"):
            print(f"  ✗ ERROR: {result.get('error')}")
            return False
        print(f"  Query valid: {result.get('valid')}")
        print(f"  Is safe: {result.get('safe')}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 12: Estimate query cost
    print("\n✓ TEST 12: estimate_query_cost(SELECT ...)")
    try:
        result = await estimate_query_cost(f"SELECT COUNT(*) FROM {test_table}")
        if not result.get("valid"):
            print(f"  ✗ ERROR: {result.get('error')}")
            return False
        print(f"  Estimated rows: {result.get('estimated_rows')}")
        print(f"  Estimated cost: {result.get('estimated_cost')}")
        print(f"  Safe to run: {result.get('safe_to_run')}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 13: Analyze query performance
    print("\n✓ TEST 13: analyze_query_performance(SELECT ...)")
    try:
        result = await analyze_query_performance(f"SELECT COUNT(*) FROM {test_table}")
        if not result.get("valid"):
            print(f"  ✗ ERROR: {result.get('error')}")
            return False
        print(f"  Actual rows: {result.get('actual_rows')}")
        print(f"  Actual time: {result.get('actual_time_ms')}ms")
        print(f"  Node type: {result.get('node_type')}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 14: Execute SQL
    print("\n✓ TEST 14: execute_sql(SELECT ...)")
    try:
        result = await execute_sql(f"SELECT COUNT(*) as total FROM {test_table}")
        if isinstance(result, list) and len(result) > 0 and "error" in str(result[0]):
            print(f"  ✗ ERROR: {result}")
            return False
        print(f"  Result: {result[0] if result else 'No results'}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 15: Set readonly
    print("\n✓ TEST 15: set_readonly(True)")
    try:
        result = await set_readonly(True)
        print(f"  Readonly mode: {result.get('readonly_mode')}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Test 16: Blocked write query
    print("\n✓ TEST 16: Verify write queries are blocked")
    try:
        result = await execute_sql("INSERT INTO users VALUES (1, 'test')")
        if isinstance(result, list) and "error" in str(result[0]):
            print(f"  ✓ Correctly blocked: {result[0].get('error', 'Unknown error')}")
        else:
            print(f"  ✗ Write query was NOT blocked!")
            return False
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    print("\n" + "=" * 80)
    print("✓ ALL TESTS PASSED!")
    print("=" * 80)
    return True

if __name__ == "__main__":
    success = asyncio.run(test_all())
    sys.exit(0 if success else 1)
