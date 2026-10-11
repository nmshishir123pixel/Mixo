import os
import openai
import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

async def test():
    client = openai.AsyncOpenAI(
        api_key=os.getenv('NVIDIA_API_KEY'),
        base_url='https://integrate.api.nvidia.com/v1'
    )
    sample_data = [
        {'style_name': 'Wireless Noise-Canceling Headphones', 'stock_count': 12, 'reorder_point': 15},
        {'style_name': 'Inomical Mechanical Keyboard', 'stock_count': 8, 'reorder_point': 10},
        {'style_name': 'Organic Cotton Heavyweight T-Shirt', 'stock_count': 25, 'reorder_point': 30},
        {'style_name': 'Smart Fitness Tracker Watch', 'stock_count': 15, 'reorder_point': 18}
    ]
    prompt = f"""You are the Chief Retail Intelligence Officer.
User Question: Which products are at risk of stockout this week?
Data Results:
{json.dumps(sample_data, indent=2)}

Provide clear, simple, plain-English executive analysis for a retail operator.
Format your response as a valid JSON object with keys:
- "insight": (2-3 concise sentences stating which products are low on stock, remaining units, and safety threshold)
- "recommendation": (1-2 concrete, high-impact tactical actions to restock)
Return ONLY the JSON object."""

    resp = await client.chat.completions.create(
        model=os.getenv('MODEL_NAME', 'nvidia/nemotron-3-super-120b-a12b'),
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=300
    )
    print("NVIDIA NIM INSIGHT RESPONSE:\n", resp.choices[0].message.content)

if __name__ == "__main__":
    asyncio.run(test())
