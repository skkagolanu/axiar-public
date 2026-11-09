import logging
from importlib import import_module
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    chromadb = import_module("chromadb")

    CHROMADB_AVAILABLE = True
except ImportError:
    logger.warning("ChromaDB not available")
    CHROMADB_AVAILABLE = False


class VectorStore:
    """ChromaDB vector store for RAG"""

    def __init__(self) -> None:
        self.client: Optional[Any] = None
        self.collection: Any = None

    def init(self) -> None:
        """Initialize ChromaDB client"""
        if not CHROMADB_AVAILABLE:
            logger.info("ChromaDB not installed, vector store disabled")
            return

        try:
            # Use new persistent client API
            self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIRECTORY)
            self.collection = self.client.get_or_create_collection(
                name="axiar_knowledge",
                metadata={"description": "Axiar business knowledge base"},
            )
            logger.info("Vector store initialized")
        except Exception as e:
            logger.info(f"Vector store unavailable: {e}")
            self.client = None

    def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]) -> None:
        """Add documents to vector store"""
        if not self.collection:
            return

        try:
            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(f"Added {len(documents)} documents to vector store")
        except Exception as e:
            logger.error(f"Failed to add documents: {e}")

    def search(self, query: str, n_results: int = 5, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for relevant documents"""
        if not self.collection:
            return []

        try:
            where_filter = {"tenant_id": tenant_id} if tenant_id else None
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
            )

            return [
                {
                    "document": doc,
                    "metadata": meta,
                    "distance": dist,
                }
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                )
            ]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []


vector_store = VectorStore()
