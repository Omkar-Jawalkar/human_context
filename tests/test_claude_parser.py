import json
import zipfile
from io import BytesIO

import pytest

from app.services.claude_parser import (
    load_conversations_from_bytes,
    parse_conversation,
    parse_conversations_payload,
)

SAMPLE_CONVERSATION = {
    "uuid": "conv-123",
    "name": "Test conversation",
    "created_at": "2026-03-05T10:30:00Z",
    "updated_at": "2026-03-05T11:45:00Z",
    "model": "claude-3-5-sonnet",
    "chat_messages": [
        {
            "uuid": "msg-1",
            "sender": "human",
            "text": "Hello",
            "created_at": "2026-03-05T10:31:00Z",
        },
        {
            "uuid": "msg-2",
            "sender": "assistant",
            "text": "Hi there",
            "created_at": "2026-03-05T10:31:05Z",
        },
    ],
}


def test_parse_conversation_extracts_messages_and_meta():
    parsed = parse_conversation(SAMPLE_CONVERSATION)
    assert parsed is not None
    assert parsed.external_uuid == "conv-123"
    assert parsed.name == "Test conversation"
    assert parsed.meta["model"] == "claude-3-5-sonnet"
    assert len(parsed.messages) == 2
    assert parsed.messages[0].sender == "human"
    assert parsed.messages[1].content == "Hi there"


def test_parse_conversations_payload_from_json_bytes():
    payload = json.dumps([SAMPLE_CONVERSATION]).encode("utf-8")
    conversations = load_conversations_from_bytes(payload)
    assert len(conversations) == 1
    assert conversations[0].external_uuid == "conv-123"


def test_load_conversations_from_zip_bytes():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("conversations.json", json.dumps([SAMPLE_CONVERSATION]))
    conversations = load_conversations_from_bytes(buffer.getvalue())
    assert len(conversations) == 1


def test_parse_conversations_payload_rejects_non_array():
    with pytest.raises(ValueError, match="JSON array"):
        parse_conversations_payload({"uuid": "bad"})
