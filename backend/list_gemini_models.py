
import asyncio
import os
import json
import aiohttp
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

async def list_models():
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not found in .env")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if resp.status == 200:
                    print("Available Models:")
                    for model in data.get("models", []):
                        print(f"- {model['name']} ({model['supportedGenerationMethods']})")
                else:
                    print(f"Error {resp.status}: {data}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(list_models())
