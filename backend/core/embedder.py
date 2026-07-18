from openai import OpenAI

class UniversalEmbedder:
    """Adapter: Ollama/OpenAI-compatible embedding endpoint."""

    def __init__(self, client: OpenAI, model: str, dimension: int) -> None:
        self._client = client
        self._model = model
        self._dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]

    @property
    def dimension(self) -> int:
        return self._dimension
