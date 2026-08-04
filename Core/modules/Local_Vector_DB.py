import os
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime
import json

class LocalVectorDB:
    def __init__(self, collection_name: str = "bolt_memory"):
        self.repo_root = Path("/Users/carter/developer/Bolt").resolve()
        self.db_path = self.repo_root / "Data" / "vector_db"
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Ollama embeddings
        self.embedding_function = embedding_functions.OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        )
        
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function
        )

    def add_documents(self, documents: list[dict]):
        """Safely add documents."""
        if not documents:
            print("⚠️  No documents to add.")
            return
        
        ids = []
        texts = []
        metadatas = []
        
        for i, doc in enumerate(documents):
            doc_id = doc.get("id") or f"doc_{int(datetime.now().timestamp())}_{i}"
            ids.append(doc_id)
            texts.append(doc["text"])
            metadatas.append(doc.get("metadata", {}))
        
        self.collection.add(ids=ids, documents=texts, metadatas=metadatas)
        print(f"✅ Added {len(documents)} documents to vector DB.")

    def search(self, query: str, n_results: int = 10, filter: dict = None):
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=filter
        )
        return [
            {
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i]
            }
            for i in range(len(results["ids"][0]))
        ]

    def refresh_from_memory(self):
        """Rebuild from memory files — fixed paths for your layout."""
        memory_dirs = [
            self.repo_root / "Data" / "data" / "memory",
            self.repo_root / "Data" / "data" / "content",
            self.repo_root / "Core",           # bolt_brain.md etc.
            self.repo_root / "Docs"
        ]
        
        documents = []
        
        for directory in memory_dirs:
            if not directory.exists():
                print(f"Skipping missing dir: {directory.name}")
                continue
                
            for md_file in directory.rglob("*.md"):
                try:
                    # Some files end in .md but aren't text (e.g. macOS Alias
                    # files dropped into the repo). Try UTF-8 first; fall back
                    # to lossy latin-1 decoding so we still get *something* to
                    # embed, then skip if it's total garbage.
                    try:
                        text = md_file.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        text = md_file.read_text(encoding="latin-1", errors="replace")
                    if len(text.strip()) < 50:
                        continue  # Skip very short or all-nonsense files
                    documents.append({
                        "id": str(md_file.relative_to(self.repo_root)),
                        "text": text[:12000],   # Large chunks are fine for Chroma
                        "metadata": {
                            "source": "memory",
                            "file": md_file.name,
                            "lane": self._guess_lane(md_file)
                        }
                    })
                except Exception as e:
                    print(f"Skipped {md_file}: {e}")
        
        print(f"Found {len(documents)} documents to index.")
        self.add_documents(documents)
        print("✅ Vector DB refresh complete.")

    def _guess_lane(self, path: Path) -> str:
        name = str(path).lower()
        if "product" in name or "amazon" in name: return "product_testing"
        if "skincare" in name or "beauty" in name: return "skincare"
        if "game" in name or "twitch" in name: return "gaming"
        if "sponsor" in name: return "sponsor"
        return "general"


# Quick test
if __name__ == "__main__":
    db = LocalVectorDB()
    db.refresh_from_memory()