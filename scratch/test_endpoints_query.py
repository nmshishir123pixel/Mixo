import sys, os
sys.path.insert(0, os.path.abspath("."))
import asyncio
from app.models.state import QueryRequest
from app.api.endpoints import query_database

async def main():
    print("--- 1. Testing Local Model ---")
    req_local = QueryRequest(
        query="Which products are at risk of stockout this week?",
        domain="retail_clothing",
        model_provider="local"
    )
    res_local = await query_database(req_local)
    print("Local SQL:", res_local.sql)
    print("Local Rows:", len(res_local.results or []))
    print("Local Metadata:", res_local.metadata)
    print("Local Status:", res_local.status)

    print("\n--- 2. Testing NVIDIA NIM API ---")
    req_nvidia = QueryRequest(
        query="Which products are at risk of stockout this week?",
        domain="retail_clothing",
        model_provider="nvidia"
    )
    res_nvidia = await query_database(req_nvidia)
    print("NVIDIA SQL:", res_nvidia.sql)
    print("NVIDIA Rows:", len(res_nvidia.results or []))
    print("NVIDIA Metadata:", res_nvidia.metadata)
    print("NVIDIA Status:", res_nvidia.status)
    print("NVIDIA Insight:", (res_nvidia.insight or "").encode('ascii', 'ignore').decode('ascii'))
    print("NVIDIA Recommendation:", (res_nvidia.recommendation or "").encode('ascii', 'ignore').decode('ascii'))

if __name__ == "__main__":
    asyncio.run(main())
