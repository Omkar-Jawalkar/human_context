import hashlib
import math
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from app.core.config import settings


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class EmbeddingService:
    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if settings.embedding_provider == "openai":
            return self._embed_openai_batch(texts)
        return [self._embed_fake(text) for text in texts]

    def embed_texts_parallel(
        self,
        texts: list[str],
        *,
        batch_size: int | None = None,
        max_workers: int | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        size = batch_size if batch_size is not None else settings.embedding_batch_size
        workers = (
            max_workers
            if max_workers is not None
            else settings.embedding_max_parallel_batches
        )

        chunks = _chunked(texts, size)
        if len(chunks) == 1 or workers <= 1:
            results: list[list[float]] = []
            for chunk in chunks:
                results.extend(self.embed_texts(chunk))
            return results

        ordered: list[list[list[float]] | None] = [None] * len(chunks)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.embed_texts, chunk): index
                for index, chunk in enumerate(chunks)
            }
            for future in as_completed(futures):
                index = futures[future]
                ordered[index] = future.result()

        results = []
        for chunk_embeddings in ordered:
            assert chunk_embeddings is not None
            results.extend(chunk_embeddings)
        return results

    def _embed_openai_batch(self, texts: list[str]) -> list[list[float]]:
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
                "input": texts,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        items = sorted(payload["data"], key=lambda item: item["index"])
        if len(items) != len(texts):
            raise ValueError(
                f"Expected {len(texts)} embeddings, got {len(items)}"
            )

        embeddings: list[list[float]] = []
        for item in items:
            embedding = item["embedding"]
            if len(embedding) != settings.embedding_dimensions:
                raise ValueError(
                    f"Expected {settings.embedding_dimensions} dimensions, got {len(embedding)}"
                )
            embeddings.append(embedding)
        return embeddings

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
