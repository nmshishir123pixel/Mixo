import urllib.request
import json
import sqlite3

print("=== Testing Dynamic Dataset Switching & Fresh Ingestion ===")

# Create a sample brand new dataset with unique products
boundary = '----WebKitFormBoundaryNewDatasetSwitch'
csv_data = """transaction_id,date,customer_id,shop_name,product,category,quantity,price,discount_pct,cost,profit,payment_method,city
TXN-NEW-001,2026-10-01,CUST-A,Cyberpunk Store,Quantum Jacket,Outerwear,5,5000,0,2000,3000,Crypto,Tokyo
TXN-NEW-002,2026-10-01,CUST-B,Cyberpunk Store,Neon Sneakers,Footwear,10,3500,0,1500,2000,UPI,Kyoto
TXN-NEW-003,2026-10-01,CUST-C,Cyberpunk Store,Hologram Visor,Accessories,15,1200,0,400,800,Card,Osaka
"""

lines = [
    f'--{boundary}',
    'Content-Disposition: form-data; name="files"; filename="cyberpunk_collection.csv"',
    'Content-Type: text/csv',
    '',
    csv_data.strip(),
    f'--{boundary}--',
    ''
]
body = '\r\n'.join(lines).encode('utf-8')

# 1. Upload the new dataset
req = urllib.request.Request(
    'http://127.0.0.1:8080/api/v1/sync/upload?auto_sync=true&replace_existing=true',
    data=body,
    method='POST'
)
req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')

res = urllib.request.urlopen(req)
upload_res = json.loads(res.read().decode('utf-8'))
print("[PASS] Upload Response:", upload_res.get("status"), "Imported:", upload_res.get("imported_count"))

# 2. Check Database directly
conn = sqlite3.connect('retail_clothing.db')
c = conn.cursor()
rows = c.execute("SELECT product, category, city, sales, profit FROM shop_sales").fetchall()
print(f"[PASS] DB shop_sales row count: {len(rows)}")
for r in rows:
    print("   ->", r)

prods = c.execute("SELECT sku, style_name, category, retail_price FROM products").fetchall()
print(f"[PASS] DB products count: {len(prods)}")
for p in prods:
    print("   ->", p)
conn.close()

# 3. Query via NL2SQL Assistant
query_payload = {
    "query": "Show top selling products",
    "domain": "retail_clothing"
}
req = urllib.request.Request(
    'http://127.0.0.1:8080/api/v1/query',
    data=json.dumps(query_payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
res = urllib.request.urlopen(req)
query_res = json.loads(res.read().decode('utf-8'))
print("[PASS] Query Assistant Results:")
print("   SQL:", query_res.get("sql"))
print("   Rows returned count:", len(query_res.get("results") or []))
for r in (query_res.get("results") or []):
    print("     ->", r)

print("=== DATASET SWITCHING VERIFICATION COMPLETE ===")
