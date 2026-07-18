import uuid
from datetime import datetime
from typing import Any, Final

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

class QdrantVectorStore:
    """Adapter: Qdrant vector database.

    Handles collection management, idempotent upserts, and semantic search.
    """

    NAMESPACE: Final = uuid.NAMESPACE_URL

    def __init__(self, client: QdrantClient, collection_name: str) -> None:
        self._client = client
        self._collection = collection_name

    def _point_id(self, job_id: str) -> str:
        return str(uuid.uuid5(self.NAMESPACE, job_id))

    def ensure_collection(self, name: str, dimension: int) -> None:
        existing = [c.name for c in self._client.get_collections().collections]
        if name not in existing:
            self._client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=dimension, distance=qmodels.Distance.COSINE
                ),
            )
            print(f"Created Qdrant collection '{name}' (dim={dimension}, cosine)")

    def upsert_jobs(self, jobs: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        points = [
            qmodels.PointStruct(id=pid, vector=vec, payload=payload)
            for pid, vec, payload in jobs
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def search_similar(
        self,
        vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        qfilter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                if isinstance(value, list):
                    conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchAny(any=value),
                        )
                    )
                else:
                    conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchValue(value=value),
                        )
                    )
            qfilter = qmodels.Filter(must=conditions)

        results = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=top_k,
            query_filter=qfilter,
            with_payload=True,
        ).points
        return [{**r.payload, "score": r.score} for r in results if r.payload]

    def get_first_seen(self, point_id: str) -> datetime | None:
        try:
            pts = self._client.retrieve(
                collection_name=self._collection,
                ids=[point_id],
                with_payload=True,
            )
            if pts:
                fs = pts[0].payload.get("first_seen_at")
                if fs:
                    return datetime.fromisoformat(fs)
        except Exception:
            pass
        return None
