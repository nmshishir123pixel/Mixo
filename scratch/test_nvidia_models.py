import os
import time
import asyncio
import openai
from dotenv import load_dotenv

load_dotenv()

client = openai.AsyncOpenAI(
    api_key=os.getenv('NVIDIA_API_KEY'),
    base_url='https://integrate.api.nvidia.com/v1'
)

# Test a set of popular models on NVIDIA NIM
test_models = [
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.1-8b-instruct",
    "meta/llama3-8b-instruct",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/llama-3.1-nemotron-51b-instruct",
    "mistralai/mistral-large-2-instruct",
    "meta/codellama-70b"
]

async def test_model(m):
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=m,
            messages=[{"role": "user", "content": "SELECT 1;"}],
            max_tokens=10,
            temperature=0.0
        )
        dt = time.time() - t0
        print(f"SUCCESS: {m} in {dt:.2f}s -> {resp.choices[0].message.content.strip()}")
        return (m, dt)
    except Exception as e:
        dt = time.time() - t0
        print(f"FAILED: {m} in {dt:.2f}s -> {str(e)[:80]}")
        return None

async def main():
    for m in test_models:
        await test_model(m)

if __name__ == '__main__':
    asyncio.run(main())
