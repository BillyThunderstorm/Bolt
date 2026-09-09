import os
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime
import json


class LocalVectorDB:
    """Chroma-backed local memory store.

    Useful embeddings require a running Ollama with an embedding model
    (default: ``nomic-embed-text``). When Ollama is unreachable the DB
    fails soft: warn + empty/no-op results so callers (Nexus, reindex,
    Think_Learn_Decide) degrade instead of raising or hanging.
    """

    def __init__(self, collection_name: str = "bolt_memory"):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.db_path = self.repo_root / "Data" / "vector_db"
        self.db_path.mkdir(parents=True, exist_ok=True)

        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.collection_name = collection_name

        self.available = False
        self.embedding_function = None
        self.client = None
        self.collection = None
        self._unavailable_reason = ""

        # Soft-connect: never raise from __init__ when Ollama is down.
        self._try_connect(warn=True)

    def _ollama_reachable(self, timeout: float = 2.0) -> bool:
        try:
            import urllib.request

            url = f"{self.ollama_host.rstrip('/')}/api/tags"
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except Exception:
            return False

    def _try_connect(self, warn: bool = False) -> bool:
        """Connect to Chroma + Ollama embeddings if possible. Soft on failure."""
        if self.available and self.collection is not None:
            return True

        if not self._ollama_reachable():
            self.available = False
            self._unavailable_reason = (
                f"Ollama not reachable at {self.ollama_host} "
                f"(needed for embeddings with model '{self.embed_model}'). "
                f"Start Ollama or run: ollama pull {self.embed_model}"
            )
            if warn:
                print(f"⚠️  Vector DB unavailable: {self._unavailable_reason}")
            return False

        try:
            self.embedding_function = embedding_functions.OllamaEmbeddingFunction(
                url=f"{self.ollama_host.rstrip('/')}/api/embeddings",
                model_name=self.embed_model,
            )
            self.client = chromadb.PersistentClient(path=str(self.db_path))
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
            )
            self.available = True
            self._unavailable_reason = ""
            return True
        except Exception as e:
            self.available = False
            self.embedding_function = None
            self.client = None
            self.collection = None
            self._unavailable_reason = str(e)
            if warn:
                print(f"⚠️  Vector DB unavailable: {e}")
            return False

    def is_available(self) -> bool:
        """True when Ollama embeddings + Chroma collection are ready."""
        return self._try_connect(warn=False)

    def add_documents(self, documents: list[dict]):
        """Safely add documents. No-op (warn) when vector backend is down."""
        if not documents:
            print("⚠️  No documents to add.")
            return False

        if not self._try_connect(warn=True):
            print("⚠️  Vector DB: skipping add (Ollama/embeddings unavailable).")
            return False

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

        try:
            self.collection.add(ids=ids, documents=texts, metadatas=metadatas)
            print(f"✅ Added {len(documents)} documents to vector DB.")
            return True
        except Exception as e:
            self.available = False
            print(f"⚠️  Vector DB add failed (soft): {e}")
            return False

    def search(self, query: str, n_results: int = 10, filter: dict = None):
        """Semantic search. Returns [] (warn) when vector backend is down."""
        if not self._try_connect(warn=True):
            print("⚠️  Vector DB: search returned empty (Ollama/embeddings unavailable).")
            return []

        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
        }
        if filter:
            kwargs["where"] = filter
        try:
            results = self.collection.query(**kwargs)
        except Exception as e:
            self.available = False
            print(f"⚠️  Vector DB search failed (soft): {e}")
            return []

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
        """Rebuild from memory files — fixed paths for your layout.

        Soft-fails (warn, no raise) when Ollama is down; does not hang.
        """
        if not self._try_connect(warn=True):
            print(
                "⚠️  Vector DB refresh skipped: Ollama/embeddings unavailable. "
                f"({self._unavailable_reason or 'see warning above'})"
            )
            return False

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
        ok = self.add_documents(documents)
        if ok:
            print("✅ Vector DB refresh complete.")
        else:
            print("⚠️  Vector DB refresh incomplete (embeddings unavailable or add failed).")
        return bool(ok)

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


# Quick test / `bolt reindex` entrypoint
if __name__ == "__main__":
    db = LocalVectorDB()
    if not db.is_available():
        print(
            f"❌ Vector DB soft-fail: {db._unavailable_reason or 'Ollama unavailable'}. "
            "Useful embeddings still need Ollama + nomic-embed-text; "
            "callers should degrade (empty search / skip enrich)."
        )
        raise SystemExit(1)
    ok = db.refresh_from_memory()
    raise SystemExit(0 if ok else 1)
