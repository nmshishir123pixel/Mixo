import sqlite3

conn = sqlite3.connect('retail_clothing.db')
c = conn.cursor()
tables = ['products', 'inventory', 'sales_events', 'shop_sales', 'suppliers', 'purchase_orders']
for t in tables:
    row = c.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{t}'").fetchone()
    if row:
        print(f"Table {t}:\n{row[0]}\n")
    else:
        print(f"Table {t} NOT FOUND\n")
