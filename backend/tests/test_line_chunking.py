"""LINE message-length handling.

LINE 400s any text over 5000 chars ("Length must be between 0 and 5000"), which
a large watchlist's daily briefing exceeds — so long messages must be split, not
sent whole.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import line_notification as ln
from app.services.line_notification import LineNotificationService


def test_short_text_is_one_chunk():
    assert ln.chunk_text("hello") == ["hello"]


def test_every_chunk_is_within_the_limit():
    text = "\n".join(f"line {i} " + "x" * 100 for i in range(200))
    chunks = ln.chunk_text(text)

    assert len(chunks) > 1
    assert all(len(c) <= ln.MAX_TEXT_LENGTH for c in chunks)


def test_split_preserves_all_content_and_breaks_on_lines():
    lines = [f"symbol {i}: some briefing text here" for i in range(400)]
    chunks = ln.chunk_text("\n".join(lines))

    # Nothing is lost, and no line is cut in half.
    rejoined = "\n".join(chunks)
    assert rejoined == "\n".join(lines)
    for chunk in chunks:
        for line in chunk.split("\n"):
            assert line in lines


def test_line_longer_than_limit_is_hard_split():
    chunks = ln.chunk_text("y" * (ln.MAX_TEXT_LENGTH * 2 + 10))
    assert all(len(c) <= ln.MAX_TEXT_LENGTH for c in chunks)
    assert "".join(chunks) == "y" * (ln.MAX_TEXT_LENGTH * 2 + 10)


@pytest.mark.asyncio
async def test_push_splits_long_message_into_message_objects():
    svc = LineNotificationService()
    long_message = "\n".join(f"stock {i}: news summary line" for i in range(500))

    response = MagicMock(status_code=200)
    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    with patch.object(ln, "get_http_client", lambda: client):
        status = await svc._call_push("Uabc", long_message)

    assert status == ln.SENT
    messages = client.post.await_args.kwargs["json"]["messages"]
    assert len(messages) > 1
    # Every object must satisfy LINE's per-message limit, or the whole push 400s.
    assert all(len(m["text"]) <= ln.MAX_TEXT_LENGTH for m in messages)
    assert all(m["type"] == "text" for m in messages)


@pytest.mark.asyncio
async def test_push_never_exceeds_five_message_objects():
    svc = LineNotificationService()
    huge = "\n".join(f"line {i} " + "z" * 200 for i in range(1000))

    response = MagicMock(status_code=200)
    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    with patch.object(ln, "get_http_client", lambda: client):
        await svc._call_push("Uabc", huge)

    messages = client.post.await_args.kwargs["json"]["messages"]
    assert len(messages) <= ln.MAX_MESSAGES_PER_PUSH
    assert all(len(m["text"]) <= ln.MAX_TEXT_LENGTH for m in messages)
    # The dropped tail is signposted rather than silently vanishing.
    assert messages[-1]["text"].endswith("… (truncated)")
