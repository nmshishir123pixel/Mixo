import os
import time
import asyncio
import openai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('NVIDIA_API_KEY')
base_url = 'https://integrate.api.nvidia.com/v1'

# Reused client
cached_client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

COMPACT_SCHEMA = """SQLite Retail Schema:
products(sku PK, style_name, category, size, color, unit_cost, retail_price)
inventory(sku PK, stock_count, reorder_point, location)
shop_sales(product, shop_name, city, quantity, sales, profit, payment_method, date)
sales_events(sku, units_sold, sale_date, channel)

Rules:
1. Valid SQLite only.
2. stockout risk: SELECT p.style_name, i.stock_count, i.reorder_point FROM products p JOIN inventory i ON p.sku = i.sku WHERE i.stock_count <= i.reorder_point;
3. top products: SELECT product, SUM(sales) AS total_sales, SUM(profit) AS total_profit FROM shop_sales GROUP BY product ORDER BY total_sales DESC;
4. sales by payment: SELECT payment_method, SUM(sales) AS total_sales FROM shop_sales GROUP BY payment_method ORDER BY total_sales DESC;
5. shop performance: SELECT shop_name, SUM(sales) AS total_sales FROM shop_sales GROUP BY shop_name ORDER BY total_sales DESC;
Return ONLY raw SQL with no markdown or explanation."""

async def benchmark():
    models_to_test = [
        "meta/llama-3.2-11b-vision-instruct",
        "mistralai/mistral-7b-instruct-v0.3"
    ]
    
    query = "Which products are at risk of stockout this week?"

    for model in models_to_test:
        print(f"\n--- Testing Model: {model} ---")
        prompt = f"{COMPACT_SCHEMA}\nQuestion: {query}\nSQL:"
        
        # Test 1: SQL Generation with max_tokens=100
        t0 = time.time()
        try:
            resp = await cached_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=80,
                stop=[";"]
            )
            t1 = time.time()
            sql = resp.choices[0].message.content.strip() + ";"
            print(f"SQL Generation Time: {t1 - t0:.2f}s")
            print(f"SQL Output: {sql}")
        except Exception as e:
            print(f"Error on {model}: {e}")

        # Test 2: Concise Insight Generation
        insight_prompt = f"""Executive Retail CIO analysis:
User asked: "{query}"
Results: 4 products below reorder point (Headphones: 12/15, Keyboard: 8/10, Watch: 15/18, T-Shirt: 25/30).
Provide 1 sentence insight and 1 sentence action. Format JSON: {{"insight": "...", "recommendation": "..."}}"""

        t2 = time.time()
        try:
            resp2 = await cached_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": insight_prompt}],
                temperature=0.0,
                max_tokens=90
            )
            t3 = time.time()
            print(f"Insight Generation Time: {t3 - t2:.2f}s")
            print(f"Insight Output: {resp2.choices[0].message.content.strip()[:100]}...")
            print(f"Total Model Latency: {(t1 - t0) + (t3 - t2):.2f}s")
        except Exception as e:
            print(f"Error on {model}: {e}")

if __name__ == "__main__":
    asyncio.run(benchmark())
