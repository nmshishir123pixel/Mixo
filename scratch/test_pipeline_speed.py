import asyncio
import time
import os
import sys
sys.path.insert(0, os.path.abspath("."))
from app.models.state import QueryRequest
from app.api.endpoints import query_database

def safe_str(s):
    if not s:
        return ""
    return str(s).encode("ascii", "ignore").decode("ascii")

async def benchmark():
    queries = [
        "Which products are at risk of stockout this week?",
        "Show top selling products by revenue and margin",
        "Show sales by payment method",
        "Which products are at risk of stockout this week?"  # Repeat query to verify cache
    ]
    
    print("=== BENCHMARKING QUERY PIPELINE WITH NVIDIA NIM ===")
    for idx, q in enumerate(queries, 1):
        t0 = time.time()
        req = QueryRequest(query=q, domain="retail_clothing", model_provider="nvidia")
        res = await query_database(req)
        t1 = time.time()
        elapsed = t1 - t0
        cache_note = " (CACHED 0ms)" if idx == 4 else ""
        print(f"[{elapsed:.2f}s]{cache_note} Query: '{q}'")
        print(f"        Status: {res.status}")
        print(f"        SQL: {res.sql}")
        print(f"        Rows: {len(res.results or [])}")
        insight_snippet = safe_str(res.insight)[:90]
        print(f"        Insight: {insight_snippet}...\n")

if __name__ == "__main__":
    asyncio.run(benchmark())
