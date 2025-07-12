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
import logging

import lancedb
import pandas as pd

from .schema import Document

TOP_K = int(os.getenv("TOP_K", "3"))
logger = logging.getLogger(__name__)


@backoff.on_exception(backoff.expo, RuntimeError, max_time=60, max_tries=3)
def add_texts_with_backoff(table, batch):
    """Add texts to LanceDB table with exponential backoff for RuntimeError failures"""
    return table.add(batch)


class InMemoryVectorStore:
    TABLE_NAME = "chunks"

    def __init__(self) -> None:
        self._db = lancedb.connect(":memory:")

        self._table = self._db.create_table(
            InMemoryVectorStore.TABLE_NAME,
            schema=Document,
            mode="overwrite",
        )
        
        # Create FTS index with error handling
        try:
            self._table.create_fts_index("text", replace=True)
        except Exception as e:
            logger.warning(f"Failed to create FTS index with replace=True: {e}")
            try:
                # Try without replace if the replace operation fails
                self._table.create_fts_index("text", replace=False)
            except Exception as e2:
                logger.warning(f"Failed to create FTS index without replace: {e2}")
                # Continue without FTS index - the table will still work but without full-text search
        
        self.texts: List[str] = []

    def add_texts(self, texts: List[str]) -> None:
        batch = []
        for t in texts:
            if t:
                batch.append({"text": t})

        if batch:
            add_texts_with_backoff(self._table, batch)
            self.texts.extend(texts)

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

    def reset(self) -> None:
        if self._table is not None:
            self._db.drop_table(self._table.name)
        self._table = None
        self.texts.clear()
