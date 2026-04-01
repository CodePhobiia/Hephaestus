"""
Vector Anti-Memory — prevents re-invention of past solutions.

Uses lancedb for vector storage and sentence-transformers for embeddings.
Storage location: ``~/.hephaestus/memory/lancedb/``

Usage::

    from hephaestus.memory.anti_memory import AntiMemory

    mem = AntiMemory()
    mem.store("Pheromone-gradient load balancer architecture...",
              metadata={"invention_name": "Pheromone LB", "source_domain": "entomology"})
    past = mem.query("I need a load balancer for traffic spikes")
    for inv in past:
        print(inv["invention_name"], inv["_distance"])
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".hephaestus" / "memory" / "lancedb"
_TABLE_NAME = "inventions"
_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class AntiMemory:
    """
    Vector Anti-Memory system.

    Stores past inventions as embeddings and retrieves similar ones
    to create an exclusion zone for the decomposer.

    Parameters
    ----------
    db_path:
        Override storage directory.  Defaults to ``~/.hephaestus/memory/lancedb/``.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._db_path.mkdir(parents=True, exist_ok=True)

        import lancedb
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(_EMBEDDING_MODEL)
        self._db = lancedb.connect(str(self._db_path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_table(self) -> Any:
        """Return the inventions table, or ``None`` if it doesn't exist yet."""
        if _TABLE_NAME in self._db.list_tables():
            return self._db.open_table(_TABLE_NAME)
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, invention_text: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Store an invention in anti-memory.

        Parameters
        ----------
        invention_text:
            Full text description of the invention (architecture, key insight, etc.).
        metadata:
            Optional dict with ``invention_name``, ``source_domain``, etc.
        """
        metadata = metadata or {}
        embedding = self._model.encode(invention_text).tolist()

        row = {
            "vector": embedding,
            "text": invention_text,
            "invention_name": metadata.get("invention_name", ""),
            "source_domain": metadata.get("source_domain", ""),
            "timestamp": time.time(),
        }

        table = self._get_table()
        if table is None:
            self._db.create_table(_TABLE_NAME, data=[row])
        else:
            table.add([row])

        logger.info(
            "Anti-memory stored: %s",
            metadata.get("invention_name", invention_text[:60]),
        )

    def query(self, problem_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Query anti-memory for past inventions similar to the given problem.

        Parameters
        ----------
        problem_text:
            The problem description to search against.
        top_k:
            Maximum number of results to return.

        Returns
        -------
        list[dict]
            Each dict has ``text``, ``invention_name``, ``source_domain``,
            and ``_distance`` (lower = more similar).
        """
        table = self._get_table()
        if table is None:
            return []

        try:
            embedding = self._model.encode(problem_text).tolist()
            results = table.search(embedding).limit(top_k).to_list()
            return [
                {
                    "text": r["text"],
                    "invention_name": r["invention_name"],
                    "source_domain": r["source_domain"],
                    "_distance": r.get("_distance", 0.0),
                }
                for r in results
            ]
        except Exception as exc:
            logger.warning("Anti-memory query failed: %s", exc)
            return []
