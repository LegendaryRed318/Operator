#!/usr/bin/env python3
"""
vault_rag.py - ChromaDB-based RAG (Retrieval-Augmented Generation) for JARVIS vault.

Provides semantic search over vault notes and documents using ChromaDB with
sentence-transformers embeddings. Enables JARVIS to answer questions based on
user's own notes and documents.

Features:
- Semantic search using all-MiniLM-L6-v2 (fast, offline, tiny model)
- Automatic indexing of all .md files in vault
- Periodic re-indexing (every 30 minutes)
- Duplicate detection to avoid re-indexing unchanged files
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from paths import VAULT_PATH

# Standard ignore patterns
IGNORE_DIRS = {
    "node_modules", ".git", ".svn", ".vscode", ".idea", "__pycache__",
    "System32", "Program Files", "Program Files (x86)", "Windows",
    "$RECYCLE.BIN", "System Volume Information", "AppData", "Temp"
}
IGNORE_EXTENSIONS = {".exe", ".dll", ".so", ".bin", ".zip", ".tar", ".gz", ".7z", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mp3", ".wav"}
SUPPORTED_EXTENSIONS = {".md", ".txt", ".py", ".js", ".ts", ".html", ".css", ".json", ".toml", ".yaml", ".yml"}

logger = logging.getLogger(__name__)

# Chunk settings
CHUNK_SIZE_WORDS = 200
CHUNK_OVERLAP_WORDS = 50


class VaultRAG:
    """ChromaDB-based RAG system for JARVIS vault."""
    
    def __init__(self, search_paths: List[str] = None):
        if search_paths is None:
            # Default to Vault + D: + E: and specific C: folders
            search_paths = [str(VAULT_PATH), "D:/", "E:/", os.path.expanduser("~/Documents"), os.path.expanduser("~/Desktop")]
        
        self.search_paths = [Path(p) for p in search_paths]
        
        # Create persistent directory for ChromaDB
        persist_dir = "C:/Projects/Operator/data/chroma_db"
        os.makedirs(persist_dir, exist_ok=True)
        
        # Use persistent client
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # Use all-MiniLM-L6-v2 - tiny (~80MB), fast, offline model
        self.embedding_func = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.collection = self.client.get_or_create_collection(
            name="jarvis_vault",
            embedding_function=self.embedding_func,
            metadata={"description": "JARVIS multi-drive knowledge base"}
        )
        
        # Track indexed files: {filepath: hash}
        self.hashes_file = Path(persist_dir) / "indexed_hashes.json"
        self._indexed_hashes: dict = self._load_hashes()
        
        # Limit paths in small mode to avoid CPU/RAM exhaustion
        mode = os.getenv("JARVIS_MODE", "small").lower()
        if mode == "small":
            logger.info("[RAG] SMALL mode detected: Limiting indexing to primary vault")
            self.search_paths = [Path(VAULT_PATH)]
        else:
            self.search_paths = [Path(p) for p in search_paths]
        
        logger.info(f"[RAG] VaultRAG initialized with {len(self.search_paths)} search roots")
    
    def _load_hashes(self) -> dict:
        """Load indexed file hashes from disk."""
        import json
        if self.hashes_file.exists():
            try:
                return json.loads(self.hashes_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"[RAG] Failed to load hashes: {e}")
        return {}

    def _save_hashes(self):
        """Save indexed file hashes to disk."""
        import json
        try:
            self.hashes_file.write_text(json.dumps(self._indexed_hashes), encoding="utf-8")
        except Exception as e:
            logger.error(f"[RAG] Failed to save hashes: {e}")
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored by the indexer."""
        # Check hidden files/folders
        if path.name.startswith("."):
            return True
        
        # Check standard ignore names
        if path.name in IGNORE_DIRS:
            return True
        
        # Check extension
        if path.suffix in IGNORE_EXTENSIONS:
            return True
        
        # Check parent folders for ignored names
        for parent in path.parents:
            if parent.name in IGNORE_DIRS:
                return True
                
        return False
    
    def _file_hash(self, filepath: Path) -> str:
        """Generate hash of file content for change detection."""
        content = filepath.read_bytes()
        return hashlib.md5(content).hexdigest()
    
    def _chunk_text(self, text: str, chunk_size: int = CHUNK_SIZE_WORDS, 
                   overlap: int = CHUNK_OVERLAP_WORDS) -> List[str]:
        """Split text into overlapping chunks by word count."""
        words = text.split()
        chunks = []
        
        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk = ' '.join(words[start:end])
            chunks.append(chunk)
            
            # Move start forward with overlap
            start = end - overlap if end < len(words) else end
            
            if start >= len(words):
                break
        
        return chunks
    
    def _extract_date_from_filename(self, filepath: Path) -> str:
        """Extract date from filename (YYYY-MM-DD pattern)."""
        import re
        match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
        return match.group(1) if match else filepath.parent.name
    
    def index_vault(self, force_reindex: bool = False) -> dict:
        """
        Index all supported files in the search paths.
        """
        logger.info("[RAG] Starting multi-drive indexing...")
        
        stats = {
            "files_indexed": 0,
            "chunks_added": 0,
            "files_skipped": 0,
            "errors": []
        }
        
        for root in self.search_paths:
            if not root.exists():
                logger.warning(f"[RAG] Search root {root} does not exist, skipping")
                continue
                
            logger.info(f"[RAG] Indexing root: {root}")
            
            # Walk the directory
            for root_dir, dirs, files in os.walk(root):
                # Filter out ignored directories in-place to stop os.walk from entering them
                dirs[:] = [d for d in dirs if not self._should_ignore(Path(root_dir) / d)]
                
                for filename in files:
                    filepath = Path(root_dir) / filename
                    
                    if filepath.suffix not in SUPPORTED_EXTENSIONS or self._should_ignore(filepath):
                        stats["files_skipped"] += 1
                        continue
                        
                    try:
                        # Check if file has changed
                        current_hash = self._file_hash(filepath)
                        file_id = str(filepath)
                        
                        if not force_reindex and file_id in self._indexed_hashes:
                            if self._indexed_hashes[file_id] == current_hash:
                                stats["files_skipped"] += 1
                                continue
                        
                        # Read and chunk file
                        try:
                            content = filepath.read_text(encoding="utf-8", errors="ignore")
                        except Exception:
                            continue # Skip files that can't be read as text
                            
                        chunks = self._chunk_text(content)
                        
                        if not chunks:
                            continue
                        
                        # Delete existing chunks for this file
                        if file_id in self._indexed_hashes:
                            self.collection.delete(
                                where={"source": file_id}
                            )
                        
                        # Add new chunks
                        for i, chunk in enumerate(chunks):
                            chunk_id = f"{file_id}_chunk_{i}"
                            
                            self.collection.add(
                                documents=[chunk],
                                ids=[chunk_id],
                                metadatas=[{
                                    "source": file_id,
                                    "file": filename,
                                    "root": str(root),
                                    "chunk_index": i,
                                    "total_chunks": len(chunks)
                                }]
                            )
                        
                        self._indexed_hashes[file_id] = current_hash
                        stats["files_indexed"] += 1
                        stats["chunks_added"] += len(chunks)
                        
                    except Exception as e:
                        logger.debug(f"[RAG] Error indexing {filepath}: {e}")
                        stats["errors"].append(str(filepath))
        
        self._save_hashes()
        logger.info(f"[RAG] Indexing complete: {stats['files_indexed']} files, "
                   f"{stats['chunks_added']} chunks")
        
        return stats
    
    def search(self, query: str, n_results: int = 3) -> List[str]:
        """
        Search vault for relevant content.
        
        Args:
            query: Search query text
            n_results: Number of results to return (default 3)
            
        Returns:
            List of matching text chunks
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "distances", "metadatas"]
            )
            
            documents = results.get("documents", [[]])[0]
            
            logger.debug(f"[RAG] Search for '{query[:50]}...': {len(documents)} results")
            
            return documents if documents else []
            
        except Exception as e:
            logger.error(f"[RAG] Search error: {e}")
            return []
    
    def add_note(self, text: str, date: Optional[str] = None) -> bool:
        """
        Add a new note directly to the collection without full re-index.
        
        Args:
            text: Note text content
            date: Date string (defaults to today)
            
        Returns:
            True if successful
        """
        try:
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            # Chunk the note
            chunks = self._chunk_text(text)
            
            # Generate unique ID based on timestamp
            timestamp = datetime.now().isoformat()
            
            for i, chunk in enumerate(chunks):
                chunk_id = f"note_{date}_{timestamp}_chunk_{i}"
                
                self.collection.add(
                    documents=[chunk],
                    ids=[chunk_id],
                    metadatas=[{
                        "source": f"notes/{date}.md",
                        "file": f"{date}.md",
                        "chunk_index": i,
                        "date": date,
                        "added_at": timestamp
                    }]
                )
            
            logger.info(f"[RAG] Added note: {len(chunks)} chunks, date {date}")
            return True
            
        except Exception as e:
            logger.error(f"[RAG] Error adding note: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Get collection statistics."""
        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "indexed_files": len(self._indexed_hashes),
                "vault_path": str(self.vault_path)
            }
        except Exception as e:
            logger.error(f"[RAG] Stats error: {e}")
            return {"error": str(e)}


async def periodic_reindex(rag: VaultRAG, interval_minutes: int = 30):
    """
    Background task to periodically re-index the vault.
    
    Args:
        rag: VaultRAG instance
        interval_minutes: Re-index interval in minutes
    """
    while True:
        try:
            await asyncio.sleep(interval_minutes * 60)
            logger.info("[RAG] Running periodic re-index...")
            stats = await asyncio.to_thread(rag.index_vault)
            logger.info(f"[RAG] Periodic re-index complete: {stats}")
        except Exception as e:
            logger.error(f"[RAG] Periodic re-index error: {e}")


# Global RAG instance (initialized by ws_server)
_vault_rag: Optional[VaultRAG] = None


def get_vault_rag() -> Optional[VaultRAG]:
    """Get the global VaultRAG instance."""
    return _vault_rag


def init_vault_rag(search_paths: List[str] = None) -> VaultRAG:
    """Initialize the global VaultRAG instance."""
    global _vault_rag
    _vault_rag = VaultRAG(search_paths)
    return _vault_rag
