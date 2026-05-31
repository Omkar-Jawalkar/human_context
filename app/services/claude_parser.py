from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from typing import Any
from zipfile import BadZipFile, ZipFile


@dataclass
class ParsedMessage:
    external_uuid: str
    sender: str
    content: str
    source_created_at: datetime | None
    sequence: int


@dataclass
class ParsedConversation:
    external_uuid: str
    name: str
    source_created_at: datetime | None
    source_updated_at: datetime | None
    meta: dict[str, Any] = field(default_factory=dict)
    messages: list[ParsedMessage] = field(default_factory=list)


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    return None


def _extract_message_text(message: dict[str, Any]) -> str:
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
        if parts:
            return "\n".join(parts).strip()

    return ""


def _message_external_uuid(message: dict[str, Any], sequence: int) -> str:
    uuid_value = message.get("uuid")
    if isinstance(uuid_value, str) and uuid_value:
        return uuid_value
    return f"seq-{sequence}"


def parse_conversation(raw: dict[str, Any]) -> ParsedConversation | None:
    external_uuid = raw.get("uuid")
    if not isinstance(external_uuid, str) or not external_uuid:
        return None

    chat_messages = raw.get("chat_messages")
    if not isinstance(chat_messages, list):
        chat_messages = []

    messages: list[ParsedMessage] = []
    for sequence, message in enumerate(chat_messages):
        if not isinstance(message, dict):
            continue

        sender = message.get("sender")
        if not isinstance(sender, str) or not sender:
            continue

        content = _extract_message_text(message)
        if not content:
            continue

        messages.append(
            ParsedMessage(
                external_uuid=_message_external_uuid(message, sequence),
                sender=sender,
                content=content,
                source_created_at=_parse_timestamp(message.get("created_at")),
                sequence=sequence,
            )
        )

    name = raw.get("name")
    conversation_name = name if isinstance(name, str) and name.strip() else "Untitled"

    meta: dict[str, Any] = {}
    for key in ("model", "project_uuid", "account"):
        if key in raw:
            meta[key] = raw[key]

    return ParsedConversation(
        external_uuid=external_uuid,
        name=conversation_name,
        source_created_at=_parse_timestamp(raw.get("created_at")),
        source_updated_at=_parse_timestamp(raw.get("updated_at")),
        meta=meta,
        messages=messages,
    )


def parse_conversations_payload(payload: Any) -> list[ParsedConversation]:
    if not isinstance(payload, list):
        raise ValueError("conversations.json must contain a JSON array")

    conversations: list[ParsedConversation] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        parsed = parse_conversation(item)
        if parsed is not None:
            conversations.append(parsed)
    return conversations


def load_conversations_from_bytes(data: bytes) -> list[ParsedConversation]:
    if data[:2] == b"PK":
        try:
            with ZipFile(BytesIO(data)) as archive:
                if "conversations.json" in archive.namelist():
                    payload = archive.read("conversations.json")
                else:
                    json_names = [name for name in archive.namelist() if name.endswith(".json")]
                    if not json_names:
                        raise ValueError("ZIP archive does not contain conversations.json")
                    payload = archive.read(json_names[0])
        except BadZipFile as exc:
            raise ValueError("Invalid ZIP archive") from exc
    else:
        payload = data

    import json

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON in conversations export") from exc

    return parse_conversations_payload(decoded)
