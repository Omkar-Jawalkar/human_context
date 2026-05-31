import hashlib
import math
import struct

import httpx

from app.core.config import settings


class EmbeddingService:
    def embed_text(self, text: str) -> list[float]:
        if settings.embedding_provider == "openai":
            return self._embed_openai(text)
        return self._embed_fake(text)

    def _embed_openai(self, text: str) -> list[float]:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when embedding_provider=openai")

        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_embedding_model,
                "input": text,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        embedding = payload["data"][0]["embedding"]
        if len(embedding) != settings.embedding_dimensions:
            raise ValueError(
                f"Expected {settings.embedding_dimensions} dimensions, got {len(embedding)}"
            )
        return embedding

    def _embed_fake(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        seed = digest

        while len(values) < settings.embedding_dimensions:
            for index in range(0, len(seed) - 3, 4):
                raw = struct.unpack("!I", seed[index : index + 4])[0]
                values.append((raw / 2**32) * 2 - 1)
                if len(values) >= settings.embedding_dimensions:
                    break
            seed = hashlib.sha256(seed).digest()

        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0:
            return values
        return [value / norm for value in values]


embedding_service = EmbeddingService()
