"""Seal a conversation from an export or pasted text, with no chat model involved."""

from __future__ import annotations

import json
import zipfile

import pytest

pytest.importorskip("starlette.testclient")
from starlette.testclient import TestClient  # noqa: E402

from epi_mcp.transcripts import NeedsChoice, TranscriptError, parse_transcript  # noqa: E402

CLAUDE_EXPORT = [
    {
        "uuid": "c1",
        "name": "Refund policy review",
        "created_at": "2026-10-01T09:00:00.000000+00:00",
        "chat_messages": [
            {"uuid": "m1", "sender": "human", "text": "Can we refund order 4411?",
             "created_at": "2026-10-01T09:00:05.000000+00:00",
             "content": [{"type": "text", "text": "Can we refund order 4411?"}], "attachments": [{"file_name": "a.pdf"}]},
            {"uuid": "m2", "sender": "assistant", "text": "Yes, it is within 30 days.",
             "created_at": "2026-10-01T09:00:09.000000+00:00",
             "content": [{"type": "text", "text": "Yes, it is within 30 days."}]},
        ],
    }
]

CHATGPT_EXPORT = [
    {
        "title": "Loan approval",
        "create_time": 1759300000.0,
        "current_node": "n4",
        "mapping": {
            "root": {"id": "root", "message": None, "parent": None, "children": ["n1"]},
            "n1": {"id": "n1", "parent": "root", "children": ["n2"],
                   "message": {"author": {"role": "system"}, "create_time": 1759300001.0,
                               "content": {"content_type": "text", "parts": ["You are a helpful assistant"]},
                               "metadata": {"is_visually_hidden_from_conversation": True}}},
            "n2": {"id": "n2", "parent": "n1", "children": ["n3"],
                   "message": {"author": {"role": "user"}, "create_time": 1759300010.0,
                               "content": {"content_type": "text", "parts": ["Approve the loan?"]}, "metadata": {}}},
            "n3": {"id": "n3", "parent": "n2", "children": ["n4", "n5"],
                   "message": {"author": {"role": "assistant"}, "create_time": 1759300020.0,
                               "content": {"content_type": "text", "parts": ["Draft: maybe."]}, "metadata": {}}},
            "n5": {"id": "n5", "parent": "n3", "children": [],
                   "message": {"author": {"role": "assistant"}, "create_time": 1759300031.0,
                               "content": {"content_type": "text", "parts": ["An abandoned branch"]}, "metadata": {}}},
            "n4": {"id": "n4", "parent": "n3", "children": [],
                   "message": {"author": {"role": "assistant"}, "create_time": 1759300030.0,
                               "content": {"content_type": "text", "parts": ["Yes, approved."]}, "metadata": {}}},
        },
    }
]


def _texts(parsed):
    return [e["content"].get("text") for e in parsed["events"] if e["kind"] in ("user.message", "assistant.message")]


def test_claude_export_is_read_exactly_with_real_times_and_source_hash():
    raw = json.dumps(CLAUDE_EXPORT)
    p = parse_transcript(raw, "conversations.json")
    assert p["how"] == "export" and p["goal"] == "Conversation: Refund policy review"
    assert _texts(p) == ["Can we refund order 4411?", "Yes, it is within 30 days."]
    kinds = [e["kind"] for e in p["events"]]
    assert kinds[0] == "artifact.attached" and p["events"][0]["content"]["sha256"] == p["source_sha256"]
    assert [e["timestamp"] for e in p["events"] if "timestamp" in e] == ["2026-10-01T09:00:05Z", "2026-10-01T09:00:09Z"]
    assert all(e["fidelity"] == "verbatim" for e in p["events"] if e["kind"].endswith(".message"))
    assert p["events"][-1]["kind"] == "redaction.omitted" and "1 attachment" in p["events"][-1]["content"]["text"]


def test_chatgpt_export_follows_the_chosen_branch_and_hides_system_text():
    p = parse_transcript(json.dumps(CHATGPT_EXPORT))
    assert _texts(p) == ["Approve the loan?", "Draft: maybe.", "Yes, approved."]
    assert "You are a helpful assistant" not in json.dumps(p["events"])
    assert "An abandoned branch" not in json.dumps(p["events"])
    times = [e["timestamp"] for e in p["events"] if "timestamp" in e]
    assert times == sorted(times) and times[0].endswith("Z")


def test_several_conversations_ask_which_one():
    both = CLAUDE_EXPORT + [dict(CLAUDE_EXPORT[0], name="Second chat")]
    with pytest.raises(NeedsChoice) as exc:
        parse_transcript(json.dumps(both))
    assert exc.value.titles == ["Refund policy review", "Second chat"]
    assert parse_transcript(json.dumps(both), choice=2)["goal"] == "Conversation: Second chat"
    with pytest.raises(NeedsChoice):
        parse_transcript(json.dumps(both), choice=9)


def test_labelled_pasted_text_becomes_turns_without_inventing_times():
    text = "You said:\nIs this allowed?\n\nChatGPT said:\nYes, with approval.\nSee policy 4.\n\nYou said:\nThanks"
    p = parse_transcript(text)
    assert p["how"] == "labelled-text"
    assert _texts(p) == ["Is this allowed?", "Yes, with approval.\nSee policy 4.", "Thanks"]
    assert not any("timestamp" in e for e in p["events"])
    inline = parse_transcript("Human: hello there\nClaude: hi, how can I help")
    assert _texts(inline) == ["hello there", "hi, how can I help"]


def test_unlabelled_text_is_sealed_as_one_attached_text_with_its_hash():
    p = parse_transcript("Just some notes without speakers.\nSecond line.", "notes.txt")
    assert p["how"] == "single-text" and len(p["events"]) == 1
    ev = p["events"][0]
    assert ev["kind"] == "artifact.attached" and ev["content"]["filename"] == "notes.txt"
    assert ev["content"]["text"].startswith("Just some notes") and len(ev["content"]["sha256"]) == 64


def test_bad_input_gets_a_plain_message():
    for bad in ("", "   \n  "):
        with pytest.raises(TranscriptError, match="empty"):
            parse_transcript(bad)
    with pytest.raises(TranscriptError, match="too large"):
        parse_transcript("x" * (3 * 1024 * 1024 + 1))
    with pytest.raises(TranscriptError, match="No readable messages"):
        parse_transcript(json.dumps([{"name": "x", "chat_messages": []}]))


@pytest.fixture
def client(monkeypatch, tmp_path):
    from epi_mcp import http, tools

    monkeypatch.setenv("EPI_OAUTH_SECRET", "s" * 40)
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "https://epi-mcp.example")
    http._SEAL_HITS.clear()
    c = TestClient(http.build_app(), raise_server_exceptions=False)
    yield c
    tools.purge_expired_artifacts(now=10**12)


def _links(html):
    import re

    view = re.search(r'href="(https://epi-mcp\.example/view/[^"]+)"', html).group(1)
    dl = re.search(r'href="(https://epi-mcp\.example/artifacts/[^"]+)"', html).group(1)
    return view.replace("https://epi-mcp.example", ""), dl.replace("https://epi-mcp.example", "")


def test_seal_page_is_public_and_explains_what_it_proves(client):
    r = client.get("/seal")  # no credentials, even though the server requires them elsewhere
    assert r.status_code == 200 and "Seal a conversation" in r.text
    assert "does not check that the text really came from" in r.text and "epilabs.org/verify" in r.text
    assert client.post("/mcp", json={}).status_code == 401  # the rest stays protected


def test_uploaded_export_is_sealed_viewable_and_verifies(client):
    r = client.post("/seal", files={"file": ("conversations.json", json.dumps(CLAUDE_EXPORT), "application/json")})
    assert r.status_code == 200 and "Sealed" in r.text and "from the assistant" in r.text
    assert "1 from you, 1 from the assistant" in r.text
    view, dl = _links(r.text)
    page = client.get(view)
    assert page.status_code == 200 and "content-security-policy" in page.headers
    saved = client.get(dl).content
    from epi_core.container import EPIContainer  # noqa: F401

    assert saved[:4] == b"<!--"
    import io

    with zipfile.ZipFile(io.BytesIO(saved)) as zf:
        steps = zf.read("steps.jsonl").decode()
        env = json.loads(zf.read("environment.json"))
    assert "Can we refund order 4411?" in steps and "Yes, it is within 30 days." in steps
    assert env["sealer_identity"]["verified"] is False


def test_pasted_text_works_and_everything_shown_back_is_escaped(client):
    evil = "<script>alert(1)</script>"
    r = client.post("/seal", data={"text": f"You: hello {evil}\nClaude: reply"})
    assert r.status_code == 200 and evil not in r.text
    big = client.post("/seal", data={"text": "x" * (3 * 1024 * 1024 + 5)})
    assert big.status_code in (400, 413) and "too large" in big.text.lower()
    multi = client.post("/seal", files={"file": ("c.json", json.dumps(CLAUDE_EXPORT + [dict(CLAUDE_EXPORT[0], name=evil)]))})
    assert multi.status_code == 200 and evil not in multi.text and "several conversations" in multi.text
    picked = client.post("/seal", data={"conversation": "1"},
                         files={"file": ("c.json", json.dumps(CLAUDE_EXPORT + [dict(CLAUDE_EXPORT[0], name="B")]))})
    assert "Sealed" in picked.text
    assert client.post("/seal", data={"text": ""}).status_code == 400


def test_seals_are_rate_limited_per_connection(client, monkeypatch):
    from epi_mcp import http

    monkeypatch.setattr(http, "_SEAL_MAX_PER_WINDOW", 2)
    ok = [client.post("/seal", data={"text": f"Human: a{i}\nClaude: b"}).status_code for i in range(2)]
    assert ok == [200, 200]
    limited = client.post("/seal", data={"text": "Human: a\nClaude: b"})
    assert limited.status_code == 429 and "Too many" in limited.text
    other = client.post("/seal", data={"text": "Human: a\nClaude: b"}, headers={"x-forwarded-for": "203.0.113.9"})
    assert other.status_code == 200


def test_a_forged_forwarded_for_prefix_does_not_dodge_the_limit(client, monkeypatch):
    from epi_mcp import http

    monkeypatch.setattr(http, "_SEAL_MAX_PER_WINDOW", 1)
    h1 = {"x-forwarded-for": "6.6.6.6, 198.51.100.7"}
    h2 = {"x-forwarded-for": "7.7.7.7, 198.51.100.7"}  # same real client, different forged prefix
    assert client.post("/seal", data={"text": "Human: a\nClaude: b"}, headers=h1).status_code == 200
    assert client.post("/seal", data={"text": "Human: a\nClaude: b"}, headers=h2).status_code == 429


# ---- real-world exports: a zip of the whole history -------------------------------------------


def _zip(files: dict[str, str]) -> bytes:
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _chat(title: str, q: str, a: str):
    return {"name": title, "uuid": title, "created_at": "2026-10-01T09:00:00Z", "chat_messages": [
        {"sender": "human", "text": q, "created_at": "2026-10-01T09:00:01Z"},
        {"sender": "assistant", "text": a, "created_at": "2026-10-01T09:00:02Z"}]}


def test_export_zip_is_read_as_downloaded_and_the_zip_hash_is_recorded():
    data = _zip({"users.json": "[]", "conversations.json": json.dumps(CLAUDE_EXPORT)})
    p = parse_transcript(data, "data-export.zip", max_bytes=30 * 1024 * 1024)
    assert p["how"] == "export" and _texts(p) == ["Can we refund order 4411?", "Yes, it is within 30 days."]
    import hashlib

    assert p["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert p["events"][0]["content"]["filename"] == "data-export.zip"
    assert p["events"][0]["content"]["conversation"] == "Refund policy review"


def test_sharded_chatgpt_export_counts_conversations_across_files():
    a = [_chat("Alpha plan", "q1", "a1"), _chat("Beta plan", "q2", "a2")]
    b = [_chat("Gamma review", "q3", "a3")]
    data = _zip({"export/conversations-000.json": json.dumps(a), "export/conversations-001.json": json.dumps(b)})
    with pytest.raises(NeedsChoice) as exc:
        parse_transcript(data, max_bytes=10**8)
    assert exc.value.total == 3 and exc.value.titles == ["Alpha plan", "Beta plan", "Gamma review"]
    assert _texts(parse_transcript(data, choice=3, max_bytes=10**8)) == ["q3", "a3"]
    assert _texts(parse_transcript(data, choice="gamma", max_bytes=10**8)) == ["q3", "a3"]  # by title
    assert _texts(parse_transcript(data, choice="2", max_bytes=10**8)) == ["q2", "a2"]


def test_a_title_that_matches_several_conversations_lists_only_those():
    items = [_chat(f"Budget {i}", f"q{i}", f"a{i}") for i in range(5)] + [_chat("Hiring", "h", "h2")]
    with pytest.raises(NeedsChoice) as exc:
        parse_transcript(json.dumps(items), choice="budget")
    assert exc.value.total == 5 and exc.value.numbers == [1, 2, 3, 4, 5]
    with pytest.raises(NeedsChoice):
        parse_transcript(json.dumps(items), choice="no such title")


def test_a_large_export_is_read_one_conversation_at_a_time():
    big = [_chat(f"Chat {i}", "question " * 50, "answer " * 200) for i in range(4000)]  # ~ 7 MB of text
    raw = json.dumps(big)
    assert len(raw) > 5 * 1024 * 1024
    import time

    t0 = time.time()
    p = parse_transcript(raw, choice=2500, max_bytes=30 * 1024 * 1024)
    assert p["goal"] == "Conversation: Chat 2499" and time.time() - t0 < 20
    assert len(p["events"]) == 3  # source hash + the two messages, not 8000


def test_zip_problems_get_plain_messages(monkeypatch):
    with pytest.raises(TranscriptError, match="No conversations.json"):
        parse_transcript(_zip({"notes.txt": "hello"}), max_bytes=10**8)
    with pytest.raises(TranscriptError, match="could not be opened"):
        parse_transcript(b"PK\x03\x04 not really a zip", max_bytes=10**8)
    with pytest.raises(TranscriptError, match="readable Claude or ChatGPT"):
        parse_transcript(_zip({"conversations.json": json.dumps([{"unrelated": 1}])}), max_bytes=10**8)
    from epi_mcp import transcripts

    monkeypatch.setattr(transcripts, "MAX_EXPORT_CHARS", 1000)  # a zip bomb: tiny file, huge contents
    bomb = _zip({"conversations.json": "[" + ",".join(["{}"] * 5000) + "]"})
    with pytest.raises(TranscriptError, match="too large to read"):
        parse_transcript(bomb, max_bytes=10**8)


def test_endpoint_accepts_a_big_export_zip_but_pasted_text_stays_small(client):
    items = [_chat(f"Chat {i}", "question " * 50, "answer " * 200) for i in range(1800)]
    data = _zip({"conversations.json": json.dumps(items)})
    assert len(json.dumps(items)) > 3 * 1024 * 1024  # bigger than the paste limit
    first = client.post("/seal", files={"file": ("export.zip", data, "application/zip")})
    assert first.status_code == 200 and "conversations" in first.text and "number" in first.text
    picked = client.post("/seal", data={"conversation": "Chat 1799"},
                         files={"file": ("export.zip", data, "application/zip")})
    assert picked.status_code == 200 and "Sealed" in picked.text and "from your chat export" in picked.text
    too_big_paste = client.post("/seal", data={"text": "x" * (3 * 1024 * 1024 + 5)})
    assert too_big_paste.status_code == 400 and "too large" in too_big_paste.text.lower()


def test_endpoint_refuses_uploads_over_the_upload_limit(client, monkeypatch):
    from epi_mcp import transcripts

    monkeypatch.setattr(transcripts, "MAX_UPLOAD_BYTES", 2000)
    r = client.post("/seal", files={"file": ("export.zip", b"PK\x03\x04" + b"0" * 5000, "application/zip")})
    assert r.status_code in (400, 413) and "too large" in r.text.lower()
