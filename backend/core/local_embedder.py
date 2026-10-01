from __future__ import annotations

from typing import Any


class LocalSentenceTransformerEmbedder:
    """Local embedding adapter using sentence-transformers; no API key required."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str | None = None,
        normalize_embeddings: bool = True,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for EMBEDDING_PROVIDER=sentence_transformers"
            ) from exc

        kwargs: dict[str, Any] = {}
        if device:
            kwargs["device"] = device
        self._model = SentenceTransformer(model_name, **kwargs)
        self._normalize = normalize_embeddings

        dimension = self._model.get_sentence_embedding_dimension()
        if dimension is None:
            probe = self._model.encode(["dimension probe"])
            dimension = len(probe[0])
        self._dimension = int(dimension)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            normalize_embeddings=self._normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    @property
    def dimension(self) -> int:
        return self._dimension
