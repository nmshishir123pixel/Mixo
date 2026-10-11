import os
import time
import asyncio
import openai
from dotenv import load_dotenv

load_dotenv()

client = openai.AsyncOpenAI(
    api_key=os.getenv('NVIDIA_API_KEY'),
    base_url='https://integrate.api.nvidia.com/v1',
    timeout=10.0
)

COMPACT_SCHEMA = """SQLite Retail Database Schema:
TABLE products (sku TEXT PRIMARY KEY, style_name TEXT, category TEXT, size TEXT, color TEXT, unit_cost REAL, retail_price REAL)
TABLE inventory (sku TEXT PRIMARY KEY, location TEXT, stock_count INTEGER, reorder_point INTEGER)
TABLE shop_sales (product TEXT, shop_name TEXT, city TEXT, quantity INTEGER, sales REAL, profit REAL, payment_method TEXT, date TEXT)
TABLE sales_events (sku TEXT, units_sold INTEGER, sale_date TEXT, channel TEXT)

Rules:
1. Valid SQLite query only. Do NOT include explanations or markdown.
2. For stockout risk: SELECT p.style_name, p.category, i.stock_count, i.reorder_point FROM products p JOIN inventory i ON p.sku = i.sku WHERE i.stock_count <= i.reorder_point;
3. For sales/top products: Use shop_sales (sales=revenue, profit=margin)."""

async def test_fast():
    queries = [
        "Which products are at risk of stockout this week?",
        "Show top selling products by revenue and margin",
        "Show sales by payment method"
    ]
    
    for q in queries:
        prompt = f"{COMPACT_SCHEMA}\nQuestion: {q}\nSQL:"
        t0 = time.time()
        resp = await client.chat.completions.create(
            model="meta/llama-3.2-11b-vision-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=80,
            stop=["\n\n", "```"]
        )
        t1 = time.time()
        sql = resp.choices[0].message.content.replace("```sql", "").replace("```", "").strip().rstrip(";") + ";"
        print(f"[{t1 - t0:.2f}s] Q: {q}")
        print(f"       SQL: {sql}\n")

if __name__ == "__main__":
    asyncio.run(test_fast())
