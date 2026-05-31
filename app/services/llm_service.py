import logging

from app.core.config import settings
from app.core.exceptions import ConfigurationError, LLMError, OpenAIAPIError
from app.core.openai_http import post_openai

logger = logging.getLogger(__name__)


class LLMService:
    def generate_answer(self, query: str, contexts: list[str]) -> str:
        if not query.strip():
            raise LLMError("Query must not be empty")

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

        try:
            payload = post_openai(
                "chat/completions",
                api_key=settings.openai_api_key,
                json_body={
                    "model": settings.openai_chat_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Answer the user's question using the provided context snippets. "
                                "If the context does not contain enough information, "
                                "say so clearly."
                            ),
                        },
                        {"role": "user", "content": user_message},
                    ],
                },
                timeout=60.0,
                operation="chat completions",
            )
        except ConfigurationError:
            raise
        except OpenAIAPIError:
            raise
        except Exception as exc:
            logger.exception("Unexpected LLM failure")
            raise LLMError(f"Chat completion request failed: {exc}") from exc

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMError("OpenAI chat response missing 'choices'")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise LLMError("OpenAI chat response missing 'message'")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError("OpenAI chat response missing assistant content")

        return content


llm_service = LLMService()
