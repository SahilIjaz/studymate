from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.conftest import FakeClaude, make_pdf


def _upload(client: TestClient, headers: dict[str, str], data: bytes, name: str = "biology.pdf") -> dict:
    response = client.post("/documents", headers=headers, files={"file": (name, data, "application/pdf")})
    assert response.status_code == 202, response.text
    return response.json()


def _events(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            events.append((name, data or {}))
    return events


def test_health_reports_configuration(client: TestClient) -> None:
    assert client.get("/").json()["health"] == "/health"
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["embedding_provider"] == "hashed-bow-384"
    assert body["llm_provider"] == "claude"
    assert body["model"] == "claude-opus-5-5"
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_workspace_header_is_required(client: TestClient) -> None:
    response = client.get("/documents")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "workspace_required"
    assert "X-Request-Id" in response.headers

    response = client.get("/documents", headers={"X-Workspace-Id": "nope"})
    assert response.status_code == 422


def test_upload_index_list_and_dedupe(client: TestClient, workspace: dict, photosynthesis_pdf: bytes) -> None:
    body = _upload(client, workspace, photosynthesis_pdf)
    doc = body["document"]
    assert body["already_indexed"] is False
    assert doc["filename"] == "biology.pdf"

    # Background indexing completes before TestClient returns.
    detail = client.get(f"/documents/{doc['id']}", headers=workspace).json()
    assert detail["status"] == "ready", detail
    assert detail["page_count"] == 2
    assert detail["chunk_count"] >= 1

    listing = client.get("/documents", headers=workspace).json()
    assert [d["id"] for d in listing["documents"]] == [doc["id"]]

    again = _upload(client, workspace, photosynthesis_pdf, name="copy.pdf")
    assert again["already_indexed"] is True
    assert again["document"]["id"] == doc["id"]


def test_upload_rejects_bad_files(client: TestClient, workspace: dict) -> None:
    response = client.post("/documents", headers=workspace, files={"file": ("x.txt", b"hello", "text/plain")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_file_type"

    response = client.post(
        "/documents", headers=workspace, files={"file": ("x.pdf", b"not a pdf", "application/pdf")}
    )
    assert response.json()["error"]["code"] == "invalid_pdf"

    scanned = make_pdf([""])  # valid PDF, no text layer
    body = _upload(client, workspace, scanned, name="scan.pdf")
    detail = client.get(f"/documents/{body['document']['id']}", headers=workspace).json()
    assert detail["status"] == "failed"
    assert "OCR" in detail["error"]


def test_ask_without_documents_is_answered_without_llm(
    client: TestClient, workspace: dict, fake_claude: FakeClaude
) -> None:
    response = client.post("/chat/ask", headers=workspace, json={"question": "What is photosynthesis?"})
    assert response.status_code == 200
    body = response.json()
    assert "haven't uploaded" in body["message"]["content"]
    assert body["message"]["citations"] == []
    assert fake_claude.calls == []


def test_ask_streams_sources_then_answer(
    client: TestClient, workspace: dict, photosynthesis_pdf: bytes, fake_claude: FakeClaude
) -> None:
    _upload(client, workspace, photosynthesis_pdf)

    with client.stream(
        "POST", "/chat/stream", headers=workspace, json={"question": "Where does photosynthesis take place?"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _events(response.read().decode())

    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names.index("sources") < names.index("delta")
    assert names[-1] == "done"

    sources = dict(events)["sources"]["sources"]
    assert sources and sources[0]["filename"] == "biology.pdf"
    assert sources[0]["page_start"] >= 1
    assert "chloroplasts" in sources[0]["text"]

    answer = "".join(payload["text"] for name, payload in events if name == "delta")
    assert answer == "The answer is in biology.pdf [1]."
    assert fake_claude.calls[0]["history"] == []

    # The conversation and both messages were persisted with citations.
    conversation_id = dict(events)["meta"]["conversation_id"]
    detail = client.get(f"/conversations/{conversation_id}", headers=workspace).json()
    assert detail["title"].startswith("Where does photosynthesis")
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["citations"][0]["n"] == 1
    assert detail["messages"][1]["usage"]["output_tokens"] == 5


def test_follow_up_carries_history_and_scoping(
    client: TestClient, workspace: dict, photosynthesis_pdf: bytes, fake_claude: FakeClaude
) -> None:
    doc = _upload(client, workspace, photosynthesis_pdf)["document"]
    first = client.post(
        "/chat/ask", headers=workspace, json={"question": "What happens in metaphase?"}
    ).json()
    convo = first["conversation_id"]

    second = client.post(
        "/chat/ask",
        headers=workspace,
        json={"question": "And anaphase?", "conversation_id": convo, "document_ids": [doc["id"]]},
    ).json()
    assert second["conversation_id"] == convo
    history = fake_claude.calls[-1]["history"]
    assert history[0] == ("user", "What happens in metaphase?")
    assert history[1][0] == "assistant"

    listing = client.get("/conversations", headers=workspace).json()["conversations"]
    assert [c["id"] for c in listing] == [convo]

    assert client.delete(f"/conversations/{convo}", headers=workspace).status_code == 204
    assert client.get(f"/conversations/{convo}", headers=workspace).status_code == 404


def test_overview_question_uses_leading_chunks(
    client: TestClient, workspace: dict, photosynthesis_pdf: bytes
) -> None:
    _upload(client, workspace, photosynthesis_pdf)
    body = client.post(
        "/chat/ask", headers=workspace, json={"question": "Summarize this document for me"}
    ).json()
    assert body["message"]["citations"]
    assert body["message"]["citations"][0]["page_start"] == 1


def test_off_topic_question_returns_no_sources(
    client: TestClient, workspace: dict, photosynthesis_pdf: bytes, fake_claude: FakeClaude
) -> None:
    _upload(client, workspace, photosynthesis_pdf)
    body = client.post("/chat/ask", headers=workspace, json={"question": "gluon quark lattice tensor"}).json()
    assert body["message"]["citations"] == []
    assert "couldn't find" in body["message"]["content"]
    assert fake_claude.calls == []


def test_workspaces_are_isolated(client: TestClient, workspace: dict, photosynthesis_pdf: bytes) -> None:
    _upload(client, workspace, photosynthesis_pdf)
    other = {"X-Workspace-Id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    assert client.get("/documents", headers=other).json()["documents"] == []
    body = client.post("/chat/ask", headers=other, json={"question": "photosynthesis"}).json()
    assert body["message"]["citations"] == []


def test_delete_document_removes_it_from_retrieval(
    client: TestClient, workspace: dict, photosynthesis_pdf: bytes
) -> None:
    doc = _upload(client, workspace, photosynthesis_pdf)["document"]
    assert client.delete(f"/documents/{doc['id']}", headers=workspace).status_code == 204
    assert client.delete(f"/documents/{doc['id']}", headers=workspace).status_code == 404
    assert client.get("/documents", headers=workspace).json()["documents"] == []
    body = client.post("/chat/ask", headers=workspace, json={"question": "photosynthesis"}).json()
    assert body["message"]["citations"] == []


def test_suggestions_endpoint(client: TestClient, workspace: dict, photosynthesis_pdf: bytes) -> None:
    doc = _upload(client, workspace, photosynthesis_pdf)["document"]
    body = client.get(f"/documents/{doc['id']}/suggestions", headers=workspace).json()
    assert len(body["questions"]) == 4


def test_rate_limit_returns_429(settings, fake_claude) -> None:
    from app.main import create_app

    settings.rate_limit_ask_per_minute = 2
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.services.claude = fake_claude
        headers = {"X-Workspace-Id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
        for _ in range(2):
            assert client.post("/chat/ask", headers=headers, json={"question": "hi"}).status_code == 200
        blocked = client.post("/chat/ask", headers=headers, json={"question": "hi"})
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"]
        assert blocked.json()["error"]["code"] == "rate_limited"


def test_api_key_gate(settings, fake_claude) -> None:
    from app.main import create_app

    settings.app_api_key = "secret"
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        headers = {"X-Workspace-Id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
        assert client.get("/documents", headers=headers).status_code == 401
        assert client.get("/documents", headers={**headers, "X-API-Key": "secret"}).status_code == 200
