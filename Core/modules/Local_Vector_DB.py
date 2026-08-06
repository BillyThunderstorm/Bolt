import os
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime
import json


class LocalVectorDB:
    """Chroma-backed local memory store. Requires a running Ollama with an
    embedding model (default: nomic-embed-text). Fails fast when Ollama is
    unreachable so callers can skip enrichment without hanging for minutes.
    """

    def __init__(self, collection_name: str = "bolt_memory"):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.db_path = self.repo_root / "Data" / "vector_db"
        self.db_path.mkdir(parents=True, exist_ok=True)

        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

        # Fail fast — chromadb's Ollama embedding calls have no useful timeout
        # and will block the whole pipeline for a long time if Ollama is down.
        if not self._ollama_reachable():
            raise RuntimeError(
                f"Ollama not reachable at {self.ollama_host} "
                f"(needed for embeddings with model '{self.embed_model}'). "
                f"Start Ollama or run: ollama pull {self.embed_model}"
            )

        self.embedding_function = embedding_functions.OllamaEmbeddingFunction(
            url=f"{self.ollama_host.rstrip('/')}/api/embeddings",
            model_name=self.embed_model,
        )

        self.client = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
        )

    def _ollama_reachable(self, timeout: float = 2.0) -> bool:
        try:
            import urllib.request

            url = f"{self.ollama_host.rstrip('/')}/api/tags"
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except Exception:
            return False

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
            # Chroma rejects empty metadata dicts inconsistently; keep a marker.
            meta = doc.get("metadata") or {}
            if not meta:
                meta = {"source": "unknown"}
            metadatas.append(meta)

        self.collection.add(ids=ids, documents=texts, metadatas=metadatas)
        print(f"✅ Added {len(documents)} documents to vector DB.")

    def search(self, query: str, n_results: int = 10, filter: dict = None):
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
        }
        if filter:
            kwargs["where"] = filter
        results = self.collection.query(**kwargs)
        if not results or not results.get("ids") or not results["ids"][0]:
            return []
        return [
            {
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
            for i in range(len(results["ids"][0]))
        ]

    def refresh_from_memory(self):
        """Rebuild from memory files — fixed paths for your layout."""
        memory_dirs = [
            self.repo_root / "Data" / "memory",
            self.repo_root / "Data" / "content",
            self.repo_root / "Data" / "data" / "memory",
            self.repo_root / "Data" / "data" / "content",
            self.repo_root / "Core",  # bolt_brain.md etc.
            self.repo_root / "Docs",
        ]

        documents = []

        for directory in memory_dirs:
            if not directory.exists():
                print(f"Skipping missing dir: {directory}")
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
                    documents.append(
                        {
                            "id": str(md_file.relative_to(self.repo_root)),
                            "text": text[:12000],  # Large chunks are fine for Chroma
                            "metadata": {
                                "source": "memory",
                                "file": md_file.name,
                                "lane": self._guess_lane(md_file),
                            },
                        }
                    )
                except Exception as e:
                    print(f"Skipped {md_file}: {e}")

        print(f"Found {len(documents)} documents to index.")
        self.add_documents(documents)
        print("✅ Vector DB refresh complete.")

    def _guess_lane(self, path: Path) -> str:
        name = str(path).lower()
        if "product" in name or "amazon" in name:
            return "product_testing"
        if "skincare" in name or "beauty" in name:
            return "skincare"
        if "game" in name or "twitch" in name:
            return "gaming"
        if "sponsor" in name:
            return "sponsor"
        return "general"


# Quick test
if __name__ == "__main__":
    try:
        db = LocalVectorDB()
        db.refresh_from_memory()
    except RuntimeError as e:
        print(f"❌ Vector DB: {e}")
        raise SystemExit(1)
