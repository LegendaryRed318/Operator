#!/usr/bin/env python3
"""
skill_multimodal.py - Multi-modal skills that process images, files, and screenshots.
"""

import base64
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from paths import LOGS_PATH, SKILLS_PATH

logger = logging.getLogger(__name__)


class MultiModalSkillProcessor:
    """Process images, files, and other non-text inputs for skills."""

    def __init__(self):
        self.supported_image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
        self.supported_document_extensions = {".pdf", ".docx", ".txt", ".md", ".rtf"}
        self.supported_audio_extensions = {".mp3", ".wav", ".m4a", ".flac"}

    def process_image(self, image_path: str) -> Dict[str, Any]:
        """Process an image and extract information."""
        path = Path(image_path)

        if not path.exists():
            return {"success": False, "error": "Image not found"}

        if path.suffix.lower() not in self.supported_image_extensions:
            return {"success": False, "error": f"Unsupported image format: {path.suffix}"}

        # Get image metadata
        try:
            stat = path.stat()
            size_kb = stat.st_size / 1024

            # Try to get image dimensions using PIL if available
            dimensions = None
            try:
                from PIL import Image
                with Image.open(path) as img:
                    dimensions = {"width": img.width, "height": img.height}
            except ImportError:
                pass

            return {
                "success": True,
                "path": str(path),
                "filename": path.name,
                "size_kb": round(size_kb, 2),
                "dimensions": dimensions,
                "format": path.suffix.lower().lstrip("."),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def analyze_image_content(self, image_path: str, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze image content using vision AI.
        Requires Gemini API or similar for actual analysis.
        """
        result = self.process_image(image_path)

        if not result["success"]:
            return result

        # If API key available, call vision API
        if api_key:
            try:
                analysis = self._call_vision_api(image_path, api_key)
                result["analysis"] = analysis
            except Exception as e:
                logger.error(f"[MultiModal] Vision API error: {e}")
                result["analysis_error"] = str(e)
        else:
            result["analysis"] = {
                "description": "Image analysis requires a vision API key",
                "suggestion": "Set GEMINI_API_KEY or AZURE_VISION_KEY in .env",
            }

        return result

    def _call_vision_api(self, image_path: str, api_key: str) -> Dict[str, Any]:
        """Call Gemini Vision API for image analysis."""
        try:
            import requests

            # Encode image
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode()

            # Gemini Vision API
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Describe this image in detail. What do you see?"},
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_data}}
                    ]
                }]
            }

            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()
            description = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")

            return {
                "description": description[:1000],
                "api": "gemini_vision",
            }

        except Exception as e:
            return {"error": str(e)}

    def process_document(self, doc_path: str) -> Dict[str, Any]:
        """Process a document and extract text/metadata."""
        path = Path(doc_path)

        if not path.exists():
            return {"success": False, "error": "Document not found"}

        if path.suffix.lower() not in self.supported_document_extensions:
            return {"success": False, "error": f"Unsupported document format: {path.suffix}"}

        try:
            stat = path.stat()
            content = None

            # Read text content
            if path.suffix.lower() in {".txt", ".md", ".rtf"}:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()[:5000]  # First 5000 chars

            elif path.suffix.lower() == ".pdf":
                # Try PyPDF2 if available
                try:
                    import PyPDF2
                    with open(path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        content = ""
                        for page in reader.pages[:5]:  # First 5 pages
                            content += page.extract_text()
                        content = content[:5000]
                except ImportError:
                    content = "PDF reading requires PyPDF2. Install with: pip install PyPDF2"

            return {
                "success": True,
                "path": str(path),
                "filename": path.name,
                "size_kb": round(stat.st_size / 1024, 2),
                "content": content,
                "word_count": len(content.split()) if content else 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def capture_screenshot(self, region: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Capture a screenshot."""
        try:
            # Use PowerShell for screenshot
            output_path = LOGS_PATH / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

            if region:
                # Region-specific screenshot (requires additional tools)
                command = f"""powershell -Command "
                    Add-Type -AssemblyName System.Windows.Forms
                    Add-Type -AssemblyName System.Drawing
                    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
                    $bitmap = $screen.Bounds
                    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
                    $graphics.CopyFromScreen({region.get('x', 0)}, {region.get('y', 0)}, 0, 0, $bitmap.Size)
                    $bitmap.Save('{output_path}')
                    $graphics.Dispose()
                    $bitmap.Dispose()
                "
                """
            else:
                # Full screen
                command = f"""powershell -Command "
                    Add-Type -AssemblyName System.Windows.Forms
                    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
                    $bitmap = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height)
                    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
                    $graphics.CopyFromScreen(0, 0, 0, 0, $bitmap.Size)
                    $bitmap.Save('{output_path}')
                    $graphics.Dispose()
                    $bitmap.Dispose()
                "
                """

            subprocess.run(command, shell=True, capture_output=True, timeout=10)

            if output_path.exists():
                return {
                    "success": True,
                    "path": str(output_path),
                    "message": "Screenshot captured",
                }
            else:
                return {"success": False, "error": "Failed to save screenshot"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def process_audio(self, audio_path: str) -> Dict[str, Any]:
        """Process an audio file and extract metadata."""
        path = Path(audio_path)

        if not path.exists():
            return {"success": False, "error": "Audio file not found"}

        if path.suffix.lower() not in self.supported_audio_extensions:
            return {"success": False, "error": f"Unsupported audio format: {path.suffix}"}

        try:
            stat = path.stat()

            # Try to get audio metadata using mutagen if available
            duration = None
            try:
                import mutagen
                audio = mutagen.File(path)
                if audio:
                    duration = audio.info.length
            except ImportError:
                pass

            return {
                "success": True,
                "path": str(path),
                "filename": path.name,
                "size_kb": round(stat.st_size / 1024, 2),
                "duration_seconds": round(duration, 2) if duration else None,
                "format": path.suffix.lower().lstrip("."),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def transcribe_audio(self, audio_path: str, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe audio to text using Whisper API."""
        result = self.process_audio(audio_path)

        if not result["success"]:
            return result

        if not api_key:
            result["transcription"] = "Transcription requires an API key (OpenAI Whisper)"
            return result

        try:
            import requests

            with open(audio_path, "rb") as f:
                files = {"file": f}
                data = {"model": "whisper-1"}
                headers = {"Authorization": f"Bearer {api_key}"}

                response = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=60
                )
                response.raise_for_status()

                result["transcription"] = response.json().get("text", "")

            return result

        except Exception as e:
            return {"success": False, "error": str(e)}


# Global processor instance
_processor: Optional[MultiModalSkillProcessor] = None


def get_multimodal_processor() -> MultiModalSkillProcessor:
    """Get or create the global multi-modal processor."""
    global _processor
    if _processor is None:
        _processor = MultiModalSkillProcessor()
    return _processor


# Multi-modal skill handlers that can be added to BUILT_IN_SKILLS
def handle_screenshot(text: str = "") -> str:
    """Capture a screenshot."""
    processor = get_multimodal_processor()
    result = processor.capture_screenshot()

    if result["success"]:
        return f"Screenshot captured and saved to {result['path']}"
    return f"Failed to capture screenshot: {result.get('error', 'Unknown error')}"


def handle_analyze_image(text: str = "") -> str:
    """Analyze an image file."""
    import re

    # Extract file path from command
    path_match = re.search(r'["\']?([A-Za-z]:\\[^"\']+|/[^"\']+)', text)

    if not path_match:
        return "Please specify an image file path. Example: 'analyze image C:\\Pictures\\photo.jpg'"

    processor = get_multimodal_processor()
    api_key = os.getenv("GEMINI_API_KEY")

    result = processor.analyze_image_content(path_match.group(1), api_key)

    if result["success"]:
        analysis = result.get("analysis", {})
        if "description" in analysis:
            return f"Image analysis: {analysis['description']}"
        return f"Image info: {result.get('filename', 'unknown')}, {result.get('size_kb', 0)}KB"

    return f"Error: {result.get('error', 'Unknown error')}"


def handle_transcribe_audio(text: str = "") -> str:
    """Transcribe an audio file."""
    import re

    path_match = re.search(r'["\']?([A-Za-z]:\\[^"\']+|/[^"\']+)', text)

    if not path_match:
        return "Please specify an audio file path. Example: 'transcribe C:\\Recordings\\meeting.mp3'"

    processor = get_multimodal_processor()
    api_key = os.getenv("OPENAI_API_KEY")

    result = processor.transcribe_audio(path_match.group(1), api_key)

    if result.get("transcription"):
        return f"Transcription: {result['transcription']}"
    elif result.get("success"):
        return "Audio processed. Transcription requires OpenAI API key."
    return f"Error: {result.get('error', 'Unknown error')}"


if __name__ == "__main__":
    # Test multi-modal processing
    logging.basicConfig(level=logging.INFO)

    print("Testing multi-modal skills...")

    processor = get_multimodal_processor()

    # Test screenshot
    print("\nCapturing screenshot...")
    result = processor.capture_screenshot()
    print(f"Screenshot: {result}")

    # Test image processing (if test image exists)
    test_image = Path.home() / "Pictures" / "test.jpg"
    if test_image.exists():
        print(f"\nAnalyzing {test_image}...")
        result = processor.analyze_image_content(str(test_image))
        print(f"Analysis: {result}")
