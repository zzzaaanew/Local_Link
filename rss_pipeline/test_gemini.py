import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

try:
    print("Available Gemini Models:")
    models = client.models.list()
    for m in models:
        if "gemini" in m.name:
            print(m.name)
except Exception as e:
    print("Error listing models:", e)
