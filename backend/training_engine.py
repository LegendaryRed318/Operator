import os
import logging
import json
import asyncio
from datetime import datetime
from pathlib import Path
from duckduckgo_search import DDGS
from paths import VAULT_PATH, LOGS_PATH

logger = logging.getLogger(__name__)

RESEARCH_PROMPT = """
# JARVIS Intelligence Report: {topic}
## Date: {date}
## Status: Deep Analysis Complete

You are JARVIS, the world's most advanced AI assistant. You have been tasked with creating a "High Quality Intelligence Report" on the topic: **{topic}**.

### THE STANDARD
Every report should leave the user feeling like they talked to the world's best-briefed analyst on that topic — someone who read everything, filtered ruthlessly, and only told them what actually matters.

### GUIDELINES
1. **Primary Sources First**: Use official documentation, whitepapers, and academic sources.
2. **Ruthless Filtering**: Do not include fluff or SEO filler. Only actionable, high-value information.
3. **Synthesis**: Connect the dots. Don't just list facts; explain why they matter to the user.
4. **Structure**: Use a clear, professional hierarchy.

### RESEARCH DATA
{research_data}

---

Generate the full report in Markdown format. Ensure it feels premium and exhaustive.
"""

class TrainingEngine:
    def __init__(self, websocket=None):
        self.ws = websocket
        self.vault_path = VAULT_PATH / "Reports"
        self.vault_path.mkdir(parents=True, exist_ok=True)

    async def generate_report(self, topic: str):
        """Perform research and generate a deep intelligence report."""
        logger.info(f"[Training] Starting research for topic: {topic}")
        
        # 1. Web Research
        search_data = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(topic, max_results=10))
                for r in results:
                    search_data.append(f"Source: {r.get('title')}\nContent: {r.get('body')}\nURL: {r.get('href')}\n")
        except Exception as e:
            logger.error(f"[Training] Search failed: {e}")
            search_data = ["Unable to reach search servers. Proceeding with internal knowledge."]

        # 2. Compile Research Data
        research_context = "\n".join(search_data)
        
        # 3. LLM Synthesis
        # We need to call the LLM. In this architecture, we'll use Gemini if available, else Ollama.
        from ws_server import call_llm
        
        full_prompt = RESEARCH_PROMPT.format(
            topic=topic,
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            research_data=research_context
        )
        
        logger.info(f"[Training] Sending research to LLM for synthesis...")
        report_content = await call_llm(full_prompt, model="gemini-1.5-flash") # Use Gemini for better synthesis
        
        # 4. Save to Vault
        file_name = f"Report_{topic.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.md"
        report_file = self.vault_path / file_name
        
        try:
            report_file.write_text(report_content, encoding="utf-8")
            logger.info(f"[Training] Report saved: {report_file}")
            
            # 5. Notify User via WS
            if self.ws:
                await self.ws.send(json.dumps({
                    "type": "response",
                    "text": f"I've completed my research on **{topic}**, sir. I've prepared a comprehensive intelligence report and filed it in your vault at `{report_file.name}`.\n\nWould you like me to summarize the key takeaways for you?",
                    "model": "jarvis:training",
                    "server_tts": False
                }))
                
            return report_file
        except Exception as e:
            logger.error(f"[Training] Failed to save report: {e}")
            return None

async def start_training_task(topic: str, websocket):
    engine = TrainingEngine(websocket)
    await engine.generate_report(topic)
