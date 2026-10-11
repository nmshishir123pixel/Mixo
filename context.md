from openai import OpenAI

client = OpenAI(
  base_url = "https://integrate.api.nvidia.com/v1",
  api_key = "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"
)

completion = client.chat.completions.create(
  model="nvidia/nemotron-3-super-120b-a12b",
  messages=[{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"Which number is larger, 9.11 or 9.8?"}],
  temperature=0.5,
  top_p=1,
  max_tokens=1024,
  stream=False
)

print(completion.choices[0].message)