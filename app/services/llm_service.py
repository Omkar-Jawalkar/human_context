import logging
import uuid
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import ConfigurationError, LLMError, OpenAIAPIError
from app.core.openai_http import post_openai

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextUserProfile:
    id: uuid.UUID
    name: str


class LLMService:
    def _persona_system_prompt(self, context_user: ContextUserProfile) -> str:
        return (
            f"You are responding as {context_user.name}, based on snippets from "
            f"their imported Claude conversations. "
            f"Speak in first person as {context_user.name} would, drawing on their "
            "past discussions. "
            f"Use the provided context snippets when relevant. If they do not contain "
            f"enough information, say so clearly as {context_user.name}. "
            "You are replying to a teammate in the Human Context app — "
            f"not to {context_user.name} directly."
        )

    def _format_rag_context_block(
        self, context_user: ContextUserProfile, rag_contexts: list[str]
    ) -> str:
        snippets = "\n\n".join(
            f"[{index + 1}] {content}"
            for index, content in enumerate(rag_contexts)
            if content
        )
        return (
            f"Context from {context_user.name}'s imported Claude history:\n{snippets}"
        )

    def generate_answer(
        self,
        query: str,
        contexts: list[str],
        *,
        context_user: ContextUserProfile | None = None,
    ) -> str:
        if not query.strip():
            raise LLMError("Query must not be empty")

        context_block = "\n\n".join(
            f"[{index + 1}] {content}"
            for index, content in enumerate(contexts)
            if content
        )

        if context_user is not None:
            system_content = self._persona_system_prompt(context_user)
            if context_block:
                user_message = (
                    f"Context from {context_user.name}'s imported Claude history:\n"
                    f"{context_block}\n\nQuestion: {query}"
                )
            else:
                user_message = f"Question: {query}"
        else:
            system_content = (
                "Answer the user's question using the provided context snippets. "
                "If the context does not contain enough information, "
                "say so clearly."
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
                        {"role": "system", "content": system_content},
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

        return self._extract_assistant_content(payload)

    def generate_chat_reply(
        self,
        *,
        thread_messages: list[tuple[str, str]],
        user_message: str,
        context_user: ContextUserProfile,
        rag_contexts: list[str] | None = None,
    ) -> str:
        if not user_message.strip():
            raise LLMError("Message must not be empty")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._persona_system_prompt(context_user)}
        ]

        if rag_contexts:
            context_block = self._format_rag_context_block(context_user, rag_contexts)
            if context_block.strip():
                messages.append({"role": "user", "content": context_block})
                messages.append(
                    {
                        "role": "assistant",
                        "content": "Understood. I will use that context when relevant.",
                    }
                )

        for role, content in thread_messages:
            messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_message})

        try:
            payload = post_openai(
                "chat/completions",
                api_key=settings.openai_api_key,
                json_body={
                    "model": settings.openai_chat_model,
                    "messages": messages,
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

        return self._extract_assistant_content(payload)

    def _extract_assistant_content(self, payload: dict) -> str:
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
