import os
import sqlite3
import asyncio
import openai
from dotenv import load_dotenv

load_dotenv()

conn = sqlite3.connect('retail_clothing.db')
c = conn.cursor()

def get_real_schema():
    tables = ['products', 'inventory', 'sales_events', 'shop_sales', 'suppliers', 'purchase_orders']
    schema_parts = []
    for t in tables:
        row = c.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{t}'").fetchone()
        if row and row[0]:
            schema_parts.append(row[0])
    return "\n\n".join(schema_parts)

real_schema = get_real_schema()

SYSTEM_PROMPT = f"""You are an elite SQL engineer for an enterprise retail business running on SQLite.
Here is the EXACT database schema:

{real_schema}

Critical SQLite Rules:
1. Write ONLY valid SQLite syntax.
2. For stockout risk or inventory questions: Join products and inventory on p.sku = i.sku. Condition: WHERE i.stock_count <= i.reorder_point. NEVER filter by last_restocked_at or any date unless explicitly asked.
3. For sales, revenue, profit, margins, top products, payment methods, shop performance, or cities: The shop_sales table has all transaction records with columns: (product, shop_name, city, quantity, sales, profit, payment_method, date).
   - In shop_sales, 'sales' is revenue and 'profit' is margin profit.
   - For top selling products: SELECT product, SUM(sales) AS total_sales, SUM(profit) AS total_profit, SUM(quantity) AS total_qty FROM shop_sales GROUP BY product ORDER BY total_sales DESC;
   - For payment methods: SELECT payment_method, SUM(sales) AS total_sales FROM shop_sales GROUP BY payment_method ORDER BY total_sales DESC;
   - For shop/store performance: SELECT shop_name, SUM(sales) AS total_sales FROM shop_sales GROUP BY shop_name ORDER BY total_sales DESC;
   - For city: SELECT city, SUM(sales) AS total_sales FROM shop_sales GROUP BY city ORDER BY total_sales DESC;
4. Return ONLY the raw SQL query with no markdown code fences, no comments, no explanation.
"""

queries = [
    "Which products are at risk of stockout this week?",
    "Show top selling products by revenue and margin",
    "Which shop had highest sales performance?",
    "Show sales by payment method",
    "What are the sales by city?"
]

async def run_tests():
    client = openai.AsyncOpenAI(
        api_key=os.getenv('NVIDIA_API_KEY'),
        base_url='https://integrate.api.nvidia.com/v1'
    )
    model = os.getenv('MODEL_NAME', 'nvidia/nemotron-3-super-120b-a12b')

    for q in queries:
        prompt = f"{SYSTEM_PROMPT}\nUser Question: {q}\nSQL:"
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=250
        )
        sql = resp.choices[0].message.content.replace("```sql", "").replace("```", "").strip().rstrip(";") + ";"
        print(f"--- Q: {q} ---")
        print(f"SQL: {sql}")
        try:
            res = c.execute(sql).fetchall()
            print(f"Result ({len(res)} rows): {res[:3]}")
            print("Status: SUCCESS\n")
        except Exception as e:
            print(f"Execution Error: {e}\nStatus: FAILED\n")

if __name__ == '__main__':
    asyncio.run(run_tests())
