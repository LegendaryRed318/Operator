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

logger = logging.getLogger(__name__)

# Chunk settings
CHUNK_SIZE_WORDS = 200
CHUNK_OVERLAP_WORDS = 50


class VaultRAG:
    """ChromaDB-based RAG system for JARVIS vault."""
    
    def __init__(self, vault_path: str = str(VAULT_PATH)):
        self.vault_path = Path(vault_path)
        
        # Create persistent directory for ChromaDB
        persist_dir = "C:/Projects/Operator/data/chroma_db"
        os.makedirs(persist_dir, exist_ok=True)
        
        # Use persistent client (saves to disk instead of memory)
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # Use all-MiniLM-L6-v2 - tiny (~80MB), fast, offline model
        self.embedding_func = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.collection = self.client.get_or_create_collection(
            name="jarvis_vault",
            embedding_function=self.embedding_func,
            metadata={"description": "JARVIS vault notes and documents"}
        )
        
        # Track indexed files: {filepath: hash} to detect changes
        self._indexed_hashes: dict = {}
        
        logger.info("[RAG] VaultRAG initialized with persistent ChromaDB")
    
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
        Index all .md files in the vault.
        
        Args:
            force_reindex: If True, re-index all files regardless of changes
            
        Returns:
            Stats dict with files_indexed, chunks_added, etc.
        """
        logger.info("[RAG] Starting vault indexing...")
        
        # Check if we already have indexed documents (persistent storage)
        existing_count = self.collection.count()
        if existing_count > 0 and not force_reindex:
            logger.info(f"[RAG] Using existing index with {existing_count} documents, skipping re-index")
            return {
                "files_indexed": 0,
                "chunks_added": 0,
                "files_skipped": existing_count,
                "errors": [],
                "using_existing": True
            }
        
        stats = {
            "files_indexed": 0,
            "chunks_added": 0,
            "files_skipped": 0,
            "errors": []
        }
        
        # Find all .md files in vault
        md_files = list(self.vault_path.rglob("*.md"))
        
        for filepath in md_files:
            try:
                # Check if file has changed
                current_hash = self._file_hash(filepath)
                file_id = str(filepath.relative_to(self.vault_path))
                
                if not force_reindex and file_id in self._indexed_hashes:
                    if self._indexed_hashes[file_id] == current_hash:
                        stats["files_skipped"] += 1
                        continue
                
                # Read and chunk file
                content = filepath.read_text(encoding="utf-8")
                chunks = self._chunk_text(content)
                
                if not chunks:
                    continue
                
                # Delete existing chunks for this file (if re-indexing)
                if file_id in self._indexed_hashes:
                    self.collection.delete(
                        where={"source": file_id}
                    )
                
                # Add new chunks
                date_str = self._extract_date_from_filename(filepath)
                
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{file_id}_chunk_{i}"
                    
                    self.collection.add(
                        documents=[chunk],
                        ids=[chunk_id],
                        metadatas=[{
                            "source": file_id,
                            "file": filepath.name,
                            "chunk_index": i,
                            "date": date_str,
                            "total_chunks": len(chunks)
                        }]
                    )
                
                self._indexed_hashes[file_id] = current_hash
                stats["files_indexed"] += 1
                stats["chunks_added"] += len(chunks)
                
                logger.debug(f"[RAG] Indexed {filepath.name}: {len(chunks)} chunks")
                
            except Exception as e:
                logger.error(f"[RAG] Error indexing {filepath}: {e}")
                stats["errors"].append(str(filepath))
        
        logger.info(f"[RAG] Indexing complete: {stats['files_indexed']} files, "
                   f"{stats['chunks_added']} chunks, {stats['files_skipped']} skipped")
        
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


def init_vault_rag(vault_path: str = str(VAULT_PATH)) -> VaultRAG:
    """Initialize the global VaultRAG instance."""
    global _vault_rag
    _vault_rag = VaultRAG(vault_path)
    return _vault_rag
