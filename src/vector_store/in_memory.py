"""
In-memory LanceDB hybrid store
──────────────────────────────
• Dense vectors  : all-mpnet-base-v2  (HuggingFace, 768-d)
• Sparse index   : BM25 on ``text`` column
• Hybrid query   : LanceDB blends BM25 + cosine in one call
• Reset support  : drops the table so UI can re-index
"""

from __future__ import annotations

import os
import uuid
from typing import List, Tuple

import backoff
import lancedb
import pandas as pd

from .schema import Document

TOP_K = int(os.getenv("TOP_K", "5"))


class InMemoryVectorStore:
    TABLE_NAME = "chunks"

    def __init__(self) -> None:
        self._db = lancedb.connect(":memory:")

        self._table = self._db.create_table(
            InMemoryVectorStore.TABLE_NAME,
            schema=Document,
            mode="overwrite",
        )
        self._table.create_fts_index("text", replace=True)
        self.texts: List[str] = []

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=5,
        giveup=lambda e: "Commit conflict" not in str(e) or "concurrent transaction" not in str(e)
    )
    def add_texts(self, texts: List[str]):
        """Add texts to the vector store with retry logic for concurrent transactions."""
        if self._table is None:
            raise RuntimeError("Vector store has been reset. Cannot add texts.")
            
        batch = []
        for t in texts:
            if t:
                batch.append({"text": t})

        if batch:
            # The vector field will be automatically populated by LanceDB's embedding function
            self._table.add(batch)
            self.texts.extend(texts)
            return len(batch)
        return 0

    def search(self, query: str, k: int = TOP_K) -> List[Tuple[str, float]]:
        if self._table is None:
            return []

        df = (
            self._table.search(
                query,
                query_type="hybrid",
            )
            .limit(k)
            .to_list()
        )

        return [(doc["text"], doc["_relevance_score"]) for doc in df]

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=5,
        giveup=lambda e: "Commit conflict" not in str(e) or "concurrent transaction" not in str(e)
    )
    def reset(self) -> None:
        """Reset the vector store with retry logic for concurrent transactions."""
        if self._table is not None:
            self._db.drop_table(self._table.name)
        self._table = None
        self.texts.clear()
