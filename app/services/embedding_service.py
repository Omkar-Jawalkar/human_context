import hashlib
import logging
import math
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.config import settings
from app.core.exceptions import ConfigurationError, EmbeddingError, OpenAIAPIError
from app.core.openai_http import post_openai

logger = logging.getLogger(__name__)


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class EmbeddingService:
    def embed_text(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingError("Cannot embed empty text")

        embeddings = self.embed_texts([text])
        if not embeddings:
            raise EmbeddingError(
                f"No embeddings returned for provider={settings.embedding_provider!r}. "
                "Set EMBEDDING_PROVIDER=openai with OPENAI_API_KEY, or use fake."
            )
        return embeddings[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        provider = settings.embedding_provider
        if provider == "openai":
            return self._embed_openai_batch(texts)
        if provider == "fake":
            return [self._embed_fake(text) for text in texts]

        raise ConfigurationError(
            f"Unsupported embedding_provider={provider!r}. Use 'openai' or 'fake'."
        )

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
                try:
                    ordered[index] = future.result()
                except (ConfigurationError, EmbeddingError, OpenAIAPIError):
                    raise
                except Exception as exc:
                    logger.exception("Parallel embedding batch %s failed", index)
                    raise EmbeddingError(
                        f"Parallel embedding batch {index} failed: {exc}"
                    ) from exc

        results: list[list[float]] = []
        for batch_index, chunk_embeddings in enumerate(ordered):
            if chunk_embeddings is None:
                raise EmbeddingError(
                    f"Parallel embedding batch {batch_index} returned no result"
                )
            results.extend(chunk_embeddings)
        return results

    def _embed_openai_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            payload = post_openai(
                "embeddings",
                api_key=settings.openai_api_key,
                json_body={
                    "model": settings.openai_embedding_model,
                    "input": texts,
                },
                timeout=60.0,
                operation="embeddings",
            )
        except ConfigurationError:
            raise
        except OpenAIAPIError:
            raise
        except Exception as exc:
            logger.exception("Unexpected embedding failure")
            raise EmbeddingError(f"Embedding request failed: {exc}") from exc

        data = payload.get("data")
        if not isinstance(data, list):
            raise EmbeddingError("OpenAI embeddings response missing 'data' list")

        items = sorted(data, key=lambda item: item.get("index", 0))
        if len(items) != len(texts):
            raise EmbeddingError(
                f"Expected {len(texts)} embeddings, got {len(items)}"
            )

        embeddings: list[list[float]] = []
        for item in items:
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise EmbeddingError("OpenAI embeddings response item missing 'embedding'")
            if len(embedding) != settings.embedding_dimensions:
                raise EmbeddingError(
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
