import urllib.request
import json
import time

time.sleep(3)

# Test Health
res = urllib.request.urlopen('http://127.0.0.1:8080/health')
print('Health status:', res.status)

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
lines = [
    f'--{boundary}',
    'Content-Disposition: form-data; name="files"; filename="test_import.csv"',
    'Content-Type: text/csv',
    '',
    'transaction_id,date,customer_id,shop_name,product,category,quantity,price,discount_pct,cost,profit,payment_method,city',
    'TXN9999,2026-09-30,CUST999,Online Store,Oversized Hoodie,Hoodies,2,1200,0,600,600,Card,Mumbai',
    f'--{boundary}--',
    ''
]
body = '\r\n'.join(lines).encode('utf-8')

for endpoint in ['http://127.0.0.1:8080/api/v1/sync/upload', 'http://127.0.0.1:8080/sync/upload']:
    req = urllib.request.Request(endpoint, data=body, method='POST')
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read().decode('utf-8'))
        print(f'[PASS] Upload to {endpoint}: status={data.get("status")}, imported={data.get("imported_count")}')
    except Exception as e:
        print(f'[FAIL] Upload to {endpoint}: {e}')
