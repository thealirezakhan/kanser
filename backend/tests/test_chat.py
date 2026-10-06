import time

from fastapi.testclient import TestClient

from app.chat import resolve_targets
from app.main import app

client = TestClient(app)


def _mk(patient="c1"):
    r = client.post(
        "/api/cases",
        json={
            "patient_ref": patient,
            "modalities": ["ct", "notes"],
            "clinical_notes": "2cm spiculated right upper lobe nodule",
        },
    )
    return r.json()["data"]["id"]


def test_resolve_targets_no_mention_defaults_to_clinical():
    assert resolve_targets("what is the stage?") == ["clinical"]


def test_resolve_targets_single_mention():
    assert resolve_targets("@radiologist what is your report?") == ["radiology"]
    assert resolve_targets("@clinician findings?") == ["clinical"]


def test_resolve_targets_all_returns_board_order():
    assert resolve_targets("@all give me your reports") == [
        "radiology",
        "pathology",
        "genomics",
        "clinical",
    ]


def test_resolve_targets_multi_mention_board_order():
    assert resolve_targets("@clinician and @radiologist please") == [
        "radiology",
        "clinical",
    ]


def test_resolve_targets_unknown_mention_falls_back():
    assert resolve_targets("@ghost hi") == ["clinical"]


def test_chat_404_unknown_case():
    r = client.post("/api/cases/nope/chat", json={"message": "hello"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_chat_validation_envelope():
    cid = _mk()
    r = client.post(f"/api/cases/{cid}/chat", json={"message": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_chat_no_mention_single_clinical_reply():
    cid = _mk("c2")
    r = client.post(
        f"/api/cases/{cid}/chat", json={"message": "summarize this case"}
    )
    assert r.status_code == 200
    turns = r.json()["data"]["turns"]
    assert len(turns) == 1
    assert turns[0]["agent"] == "clinical"
    assert "Dr. Care" in turns[0]["name"]


def test_chat_mention_radiologist_only_radiology():
    cid = _mk("c3")
    r = client.post(
        f"/api/cases/{cid}/chat",
        json={"message": "@radiologist what is your report?"},
    )
    turns = r.json()["data"]["turns"]
    assert [t["agent"] for t in turns] == ["radiology"]
    assert turns[0]["text"]


def test_chat_all_turns_in_board_order_with_tokens():
    cid = _mk("c4")
    r = client.post(
        f"/api/cases/{cid}/chat", json={"message": "@all give me your reports"}
    )
    data = r.json()["data"]
    assert [t["agent"] for t in data["turns"]] == [
        "radiology",
        "pathology",
        "genomics",
        "clinical",
    ]
    for t in data["turns"]:
        assert t["tokens_in"] > 0
        assert t["tokens_out"] > 0
        assert len(t["text"]) <= 800
    assert data["tokens"]["radiology"]["out"] > 0
    assert data["tokens"]["clinical"]["out"] > 0


def test_chat_context_built_once_per_case():
    cid = _mk("c5")
    first = client.post(f"/api/cases/{cid}/chat", json={"message": "hello"})
    assert first.json()["data"]["context_builds"] == 1
    second = client.post(f"/api/cases/{cid}/chat", json={"message": "again"})
    assert second.json()["data"]["context_builds"] == 1


def test_chat_context_invalidated_after_upload():
    cid = _mk("c5a")
    first = client.post(f"/api/cases/{cid}/chat", json={"message": "hello"})
    assert first.json()["data"]["context_builds"] == 1
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("addendum.txt", b"PDL1 80 percent, EGFR negative", "text/plain")},
        data={"case_id": cid},
    )
    assert r.status_code == 201
    second = client.post(f"/api/cases/{cid}/chat", json={"message": "latest?"})
    assert second.json()["data"]["context_builds"] == 2


def test_chat_context_invalidated_after_new_run():
    cid = _mk("c5b")
    first = client.post(f"/api/cases/{cid}/chat", json={"message": "hello"})
    assert first.json()["data"]["context_builds"] == 1
    from app.chat import invalidate_context

    invalidate_context(cid)
    second = client.post(f"/api/cases/{cid}/chat", json={"message": "again"})
    assert second.json()["data"]["context_builds"] == 2


def test_chat_history_bounded():
    cid = _mk("c6")
    for i in range(12):
        r = client.post(f"/api/cases/{cid}/chat", json={"message": f"question {i}"})
    data = r.json()["data"]
    assert data["history_size"] <= 16  # 8 exchanges x (user + reply)


def test_chat_ws_group_turns():
    from app.auth import create_token

    token = create_token("admin")
    cid = _mk("c7")
    with client.websocket_connect(f"/ws/cases/{cid}/chat") as ws:
        ws.send_json({"type": "auth", "token": token})
        ws.send_json({"message": "@all give me your reports"})
        seen = []
        deadline = time.time() + 30
        while time.time() < deadline:
            ev = ws.receive_json()
            if ev["type"] == "chat_turn":
                seen.append(ev["agent"])
            if ev["type"] == "chat_done":
                break
    assert seen == ["radiology", "pathology", "genomics", "clinical"]
