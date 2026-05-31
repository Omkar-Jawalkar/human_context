import httpx

from app.core.config import settings


class LLMService:
    def generate_answer(self, query: str, contexts: list[str]) -> str:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for chat completions")

        context_block = "\n\n".join(
            f"[{index + 1}] {content}"
            for index, content in enumerate(contexts)
            if content
        )
        user_message = (
            f"Context:\n{context_block}\n\nQuestion: {query}"
            if context_block
            else f"Question: {query}"
        )

        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_chat_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Answer the user's question using the provided context snippets. "
                            "If the context does not contain enough information, say so clearly."
                        ),
                    },
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]


llm_service = LLMService()
