"""
rag_memory.py - ChromaDB semantic search vector storage for Jarvis.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_chroma_client = None
_collection = None

def get_chroma_collection():
    global _chroma_client, _collection
    if _collection is not None:
        return _collection
    
    try:
        import chromadb
        
        db_path = Path(__file__).parent / ".chromadata"
        db_path.mkdir(exist_ok=True)
        
        _chroma_client = chromadb.PersistentClient(path=str(db_path))
        _collection = _chroma_client.get_or_create_collection(name="jarvis_vault")
        return _collection
    except ImportError:
        logger.error("[RAG] ChromaDB not installed. Run: pip install chromadb")
        return None
    except Exception as e:
        logger.error(f"[RAG] Failed to init ChromaDB: {e}")
        return None

def ingest_vault(vault_root: Path):
    """
    Scans the markdown files and syncs them to ChromaDB.
    This creates an offline local copy of the Second Brain for quick vector search.
    """
    collection = get_chroma_collection()
    if not collection: return
    
    try:
        # Use simple text chunking (langchain text splitter if present, or fallback)
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        except ImportError:
            # Fallback simple splitter
            class SimpleSplitter:
                def split_text(self, text):
                    chunks = []
                    lines = text.split('\n')
                    chunk = ""
                    for line in lines:
                        if len(chunk) + len(line) > 1000:
                            chunks.append(chunk)
                            chunk = line
                        else:
                            chunk += "\n" + line
                    if chunk: chunks.append(chunk)
                    return chunks
            splitter = SimpleSplitter()

        documents = []
        metadatas = []
        ids = []
        
        # Read ALL md files
        for md_file in vault_root.rglob("*.md"):
            try:
                rel_path = str(md_file.relative_to(vault_root)).replace("\\", "/")
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                if not content.strip(): continue
                
                chunks = splitter.split_text(content)
                for i, chunk in enumerate(chunks):
                    if not chunk.strip(): continue
                    documents.append(chunk)
                    metadatas.append({"source": rel_path})
                    ids.append(f"{rel_path}_{i}")
                    
            except Exception as e:
                logger.warning(f"[RAG] Failed to read {md_file}: {e}")
        
        if documents:
            # Upsert into Chroma (batching for large vaults)
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                collection.upsert(
                    documents=documents[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size],
                    ids=ids[i:i+batch_size]
                )
            logger.info(f"[RAG] Successfully ingested {len(documents)} chunks from {vault_root}")
    except Exception as e:
        logger.error(f"[RAG] Ingestion failed: {e}")

def semantic_search(query: str, n_results: int = 5) -> list:
    """
    Search the embedded chunks for semantic matches to the query.
    """
    collection = get_chroma_collection()
    if not collection: return []
    
    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        formatted_results = []
        if results and results['documents'] and results['documents'][0]:
            docs = results['documents'][0]
            metas = results['metadatas'][0]
            
            for doc, meta in zip(docs, metas):
                formatted_results.append({
                    "file": meta.get("source", "Unknown"),
                    "excerpt": doc[:200].replace("\n", " ") + "...",
                    "relevance_score": 100 # Semantic results
                })
        return formatted_results
    except Exception as e:
        logger.error(f"[RAG] Search failed: {e}")
        return []
