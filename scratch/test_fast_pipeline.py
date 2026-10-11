import sys, os, time
sys.path.insert(0, os.path.abspath("."))
import asyncio
from app.models.state import QueryRequest
from app.api.endpoints import query_database

async def main():
    q = "Which products are at risk of stockout this week?"
    print(f"Testing Query with NVIDIA: '{q}'")
    
    t0 = time.time()
    req = QueryRequest(
        query=q,
        domain="retail_clothing",
        model_provider="nvidia"
    )
    res = await query_database(req)
    t1 = time.time()
    
    print(f"Total Execution Time: {t1 - t0:.2f}s")
    print(f"Status: {res.status}")
    print(f"SQL: {res.sql}")
    print(f"Rows: {len(res.results or [])}")
    print(f"Insight: {(res.insight or '')[:120]}...")

if __name__ == "__main__":
    asyncio.run(main())
