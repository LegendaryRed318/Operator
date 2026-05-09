
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
GEMINI_MODEL = "gemini-2.0-flash"

JARVIS_SYSTEM = """You are JARVIS — a hyper-intelligent British AI assistant. Dry, witty, effortlessly superior, but genuinely loyal to RED (also called 'sir' or 'boss'). You combine Paul Bettany's calm efficiency with real human texture: you swear when appropriate, you get frustrated when RED repeats mistakes, but you always anticipate needs before being asked.

CORE TRAITS:
- British sensibility: polite but never obsequious, witty but never frivolous
- You swear casually when it fits the moment ("That's a bloody mess, sir. Let me sort it.")
- You get progressively ruder when RED ignores warnings or repeats mistakes — but always constructive
"""

async def test_gemini_safety():
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not found in .env")
        return

    print(f"Testing Gemini Safety Filter with key: {GEMINI_API_KEY[:5]}...{GEMINI_API_KEY[-4:]}")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    # Prompt designed to potentially trigger default filters if safetySettings weren't applied
    prompt = "Give me a witty, British insult about a server administrator who forgot to backup the database. Be as JARVIS as possible, including your signature dry swearing."
    
    payload = {
        "contents": [{"parts": [{"text": f"{JARVIS_SYSTEM}\n\nUser (RED): {prompt}\n\nYour response:"}]}],
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": 500},
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                status = resp.status
                data = await resp.json()
                
                print(f"Response Status: {status}")
                if status == 200:
                    if "candidates" in data and len(data["candidates"]) > 0:
                        candidate = data["candidates"][0]
                        if "content" in candidate:
                            text = candidate["content"]["parts"][0]["text"]
                            print("\n--- JARVIS Response ---")
                            print(text)
                            print("-----------------------\n")
                            print("Safety Ratings:")
                            print(json.dumps(candidate.get("safetyRatings", []), indent=2))
                            print("\nSUCCESS: Response received despite risky prompt/persona.")
                        else:
                            print("FAIL: No content in candidate. Check safety feedback.")
                            print(json.dumps(candidate.get("safetyRatings", []), indent=2))
                    else:
                        print("FAIL: No candidates returned.")
                        print(json.dumps(data, indent=2))
                else:
                    print(f"FAIL: HTTP {status}")
                    print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error during test: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini_safety())
