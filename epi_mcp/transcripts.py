"""Turn a chat export or pasted conversation into sealable events, with no model involved.

Why this exists: sealing through a chat host means the model re-types the whole
conversation into a tool call. Hosts can pause that, and a model re-typing text can
shorten it or get times wrong. Taking the text straight from the person's own export
or paste gives the exact words and real times, and cannot be paused.

Supported, best effort (the page shows a preview before anything is sealed):
- Claude export (conversations.json): ``chat_messages`` with ``sender`` human/assistant
- ChatGPT export (conversations.json): ``mapping`` tree walked from ``current_node``
- Pasted text with speaker labels (You/Human/User ... ChatGPT/Claude/Assistant)
- Anything else: sealed as one attached text with its SHA-256

What is sealed is exactly what the person supplied. EPI does not check that it really
came from Claude or ChatGPT; the seal proves it has not changed since it was sealed.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

MAX_INPUT_BYTES = 3 * 1024 * 1024
_USER_LABELS = r"(?:you said|you|human|user|me|question)"
_ASSISTANT_LABELS = r"(?:chatgpt said|chatgpt|claude responded|claude said|claude|assistant|ai|answer)"
_LABEL_RE = re.compile(
    rf"^\s*(?P<who>{_USER_LABELS}|{_ASSISTANT_LABELS})\s*:?\s*$|"
    rf"^\s*(?P<who2>{_USER_LABELS}|{_ASSISTANT_LABELS})\s*:\s+(?P<rest>.+)$",
    re.IGNORECASE,
)
_USER_RE = re.compile(rf"^{_USER_LABELS}$", re.IGNORECASE)


class TranscriptError(ValueError):
    """The input could not be read. The message is safe to show to the person."""


class NeedsChoice(TranscriptError):
    """The export holds several conversations; the person must pick one."""

    def __init__(self, titles: list[str]):
        self.titles = titles
        super().__init__(f"This file contains {len(titles)} conversations. Choose one.")


def _iso(value: Any) -> str | None:
    """ISO-8601 UTC from an epoch number or an ISO string; None when absent."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return None


def _event(kind: str, text: str, when: Any = None) -> dict[str, Any]:
    ev: dict[str, Any] = {"kind": kind, "content": {"text": text}, "fidelity": "verbatim"}
    ts = _iso(when)
    if ts:
        ev["timestamp"] = ts
    return ev


def _claude_conversation(conv: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    skipped = 0
    for msg in conv.get("chat_messages") or []:
        if not isinstance(msg, dict):
            continue
        blocks = msg.get("content")
        text = ""
        if isinstance(blocks, list):
            text = "\n".join(
                str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
        if not text:
            text = str(msg.get("text") or "").strip()
        if msg.get("attachments") or msg.get("files"):
            skipped += len(msg.get("attachments") or []) + len(msg.get("files") or [])
        if not text:
            continue
        kind = "user.message" if msg.get("sender") == "human" else "assistant.message"
        events.append(_event(kind, text, msg.get("created_at")))
    return events, skipped


def _chatgpt_conversation(conv: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    mapping = conv.get("mapping") or {}
    node_id = conv.get("current_node")
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    while node_id and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        node = mapping[node_id]
        chain.append(node)
        node_id = node.get("parent")
    events: list[dict[str, Any]] = []
    skipped = 0
    for node in reversed(chain):
        msg = node.get("message")
        if not isinstance(msg, dict):
            continue
        role = (msg.get("author") or {}).get("role")
        if role not in ("user", "assistant"):
            continue
        meta = msg.get("metadata") or {}
        if meta.get("is_visually_hidden_from_conversation"):
            continue
        content = msg.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        text = ""
        if isinstance(parts, list):
            text = "\n".join(p for p in parts if isinstance(p, str)).strip()
            skipped += sum(1 for p in parts if not isinstance(p, str))
        if not text:
            continue
        kind = "user.message" if role == "user" else "assistant.message"
        events.append(_event(kind, text, msg.get("create_time")))
    return events, skipped


def _title(conv: dict[str, Any]) -> str:
    return str(conv.get("name") or conv.get("title") or "Untitled conversation")


def _from_json(data: Any, choice: int | None) -> tuple[list[dict[str, Any]], str, int] | None:
    convs: list[dict[str, Any]]
    if isinstance(data, dict) and ("chat_messages" in data or "mapping" in data):
        convs = [data]
    elif isinstance(data, list) and data and all(isinstance(c, dict) for c in data) and any(
        "chat_messages" in c or "mapping" in c for c in data
    ):
        convs = [c for c in data if "chat_messages" in c or "mapping" in c]
    else:
        return None
    if len(convs) > 1:
        if choice is None or not 1 <= choice <= len(convs):
            raise NeedsChoice([_title(c) for c in convs])
        conv = convs[choice - 1]
    else:
        conv = convs[0]
    events, skipped = _claude_conversation(conv) if "chat_messages" in conv else _chatgpt_conversation(conv)
    if not events:
        raise TranscriptError("No readable messages were found in that conversation.")
    return events, _title(conv), skipped


def _from_labelled_text(text: str) -> list[dict[str, Any]] | None:
    turns: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        m = _LABEL_RE.match(line)
        if m:
            who = (m.group("who") or m.group("who2") or "").strip()
            kind = "user.message" if _USER_RE.match(who) else "assistant.message"
            turns.append((kind, [m.group("rest")] if m.group("rest") else []))
        elif turns:
            turns[-1][1].append(line)
    events = []
    for kind, lines in turns:
        body = "\n".join(lines).strip()
        if body:
            events.append(_event(kind, body))
    kinds = {e["kind"] for e in events}
    if len(events) >= 2 and len(kinds) == 2:
        return events
    return None


def parse_transcript(raw: bytes | str, filename: str = "", choice: int | None = None) -> dict[str, Any]:
    """Return {events, goal, source_sha256, how, skipped}. Raises TranscriptError."""
    data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    if not data.strip():
        raise TranscriptError("Nothing to seal: the file or text is empty.")
    if len(data) > MAX_INPUT_BYTES:
        raise TranscriptError(
            f"That is too large ({len(data) // (1024 * 1024)} MB; the limit is {MAX_INPUT_BYTES // (1024 * 1024)} MB). "
            "Export or paste a single conversation."
        )
    text = data.decode("utf-8", errors="replace").lstrip("﻿")
    source_sha = hashlib.sha256(data).hexdigest()
    skipped = 0
    how = "text"
    goal = "Conversation sealed from a file or text provided by the person who sealed it"

    events: list[dict[str, Any]] | None = None
    if text.lstrip()[:1] in "[{":
        try:
            parsed = _from_json(json.loads(text), choice)
        except json.JSONDecodeError:
            parsed = None
        if parsed:
            events, title, skipped = parsed
            how = "export"
            goal = f"Conversation: {title[:120]}"
    if events is None:
        events = _from_labelled_text(text)
        if events:
            how = "labelled-text"
    if events is None:
        name = (filename or "pasted-text.txt").strip() or "pasted-text.txt"
        events = [
            {
                "kind": "artifact.attached",
                "content": {"filename": name, "sha256": source_sha, "text": text},
                "fidelity": "verbatim",
            }
        ]
        how = "single-text"

    head = {
        "kind": "artifact.attached",
        "content": {
            "filename": (filename or "pasted-text.txt"),
            "sha256": source_sha,
            "note": "The original file or text supplied by the person who sealed it; the messages below were read from it.",
        },
        "fidelity": "hash_only",
    }
    if how == "single-text":
        out = events  # the attached text already carries the hash
    else:
        out = [head] + events
    if skipped:
        out.append(
            {
                "kind": "redaction.omitted",
                "content": {"text": f"{skipped} attachment(s) or non-text item(s) in the export were not included."},
            }
        )
    return {"events": out, "goal": goal, "source_sha256": source_sha, "how": how, "skipped": skipped}
