import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
try:
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}]
    )
    print("Haiku success:", response.content[0].text)
except Exception as e:
    print("Haiku error:", e)

try:
    response = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}]
    )
    print("Sonnet 3.5 success:", response.content[0].text)
except Exception as e:
    print("Sonnet 3.5 error:", e)
    
try:
    response = client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}]
    )
    print("Sonnet 3.0 success:", response.content[0].text)
except Exception as e:
    print("Sonnet 3.0 error:", e)
