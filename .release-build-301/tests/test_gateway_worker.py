import json

from epi_core.case_store import build_case_payload_from_events
from epi_gateway.worker import EvidenceWorker


def test_worker_flush_batch_persists_events_and_projects_cases(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=5, batch_timeout=0.5)

    worker._flush_batch(  # noqa: SLF001 - targeted persistence check
        [
            {
                "kind": "llm.request",
                "content": {"prompt": "Approve refund"},
                "meta": {"trace_id": "trace-1", "source": "gateway-test"},
            },
            {
                "kind": "llm.response",
                "content": {"output_text": "Escalate for review"},
                "meta": {"trace_id": "trace-1", "source": "gateway-test"},
            },
        ]
    )

    files = list((tmp_path / "events").glob("evidence_*.json"))
    assert len(files) == 1

    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["_signed_batch"] is True
    assert payload["count"] == 2
    assert payload["items"][0]["event_id"].startswith("evt_")
    assert payload["items"][0]["trace_id"] == "trace-1"
    assert payload["items"][0]["provenance"]["source"] == "gateway-test"

    cases = worker.list_cases()
    assert len(cases) == 1
    assert cases[0]["trace_id"] == "trace-1"
    assert worker.get_case(cases[0]["id"])["backend_case"] is True


def test_worker_snapshot_reports_runtime_configuration_and_case_store(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=7, batch_timeout=1.5)

    snapshot = worker.snapshot()

    assert snapshot["queue_size"] == 0
    assert snapshot["processed_count"] == 0
    assert snapshot["storage_dir"] == str(tmp_path)
    assert snapshot["events_dir"] == str(tmp_path / "events")
    assert snapshot["database_path"] == str(tmp_path / "cases.sqlite3")
    assert snapshot["batch_size"] == 7
    assert snapshot["batch_timeout"] == 1.5
    assert snapshot["case_count"] == 0


def test_worker_replay_is_idempotent(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path)
    touched = worker.store_items(
        [
            {
                "kind": "policy.check",
                "content": {"allowed": False, "rule_id": "R001"},
                "meta": {"decision_id": "decision-1"},
            }
        ]
    )
    assert touched

    replayer = EvidenceWorker(storage_dir=tmp_path)
    replay = replayer.case_store.replay_spool(tmp_path / "events")

    assert replay.applied_batches == 0
    assert replay.skipped_batches == 1
    assert len(replayer.list_cases()) == 1


def test_worker_replay_quarantines_corrupt_spool_files(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    corrupt_file = events_dir / "evidence_bad.json"
    corrupt_file.write_text("{not-json", encoding="utf-8")

    worker = EvidenceWorker(storage_dir=tmp_path)
    replay = worker.case_store.replay_spool(events_dir)

    assert replay.applied_batches == 0
    assert replay.corrupt_batch_count == 1
    assert replay.corrupt_files == ["evidence_bad.json"]
    assert replay.moved_corrupt_files
    assert not corrupt_file.exists()
    assert (events_dir / "corrupt" / replay.moved_corrupt_files[0]).exists()


def test_worker_workflow_state_comments_and_activity_persist(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    touched = worker.store_items(
        [
            {
                "kind": "policy.check",
                "content": {"allowed": False, "rule_id": "R001"},
                "meta": {"decision_id": "decision-42", "workflow_name": "Refund approvals"},
            }
        ]
    )
    case_id = touched[0]

    initial = worker.get_case(case_id)
    assert initial["status"] == "unassigned"

    updated = worker.update_case_workflow(
        case_id,
        {
            "assignee": "ops@epilabs.org",
            "due_at": "2026-03-28",
            "status": "assigned",
            "updated_by": "lead@epilabs.org",
            "reason": "Queue handoff",
        },
    )
    assert updated["assignee"] == "ops@epilabs.org"
    assert updated["due_at"] == "2026-03-28"
    assert updated["status"] == "assigned"

    commented = worker.add_comment(case_id, "ops@epilabs.org", "Need finance confirmation.")
    assert len(commented["comments"]) == 1
    assert commented["comments"][0]["body"] == "Need finance confirmation."

    reviewed = worker.save_review(
        case_id,
        {
            "review_version": "1.0.0",
            "reviewed_by": "ops@epilabs.org",
            "reviewed_at": "2026-03-27T12:00:00Z",
            "reviews": [
                {
                    "outcome": "dismissed",
                    "notes": "Approved after manual check.",
                    "reviewer": "ops@epilabs.org",
                    "timestamp": "2026-03-27T12:00:00Z",
                }
            ],
        },
    )
    assert reviewed["status"] == "resolved"
    activity_kinds = [item["kind"] for item in reviewed["activity"]]
    assert "assignment_changed" in activity_kinds
    assert "due_date_changed" in activity_kinds
    assert "status_changed" in activity_kinds
    assert "comment_added" in activity_kinds
    assert "review_saved" in activity_kinds

    restarted = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    restarted.start()
    try:
        persisted = restarted.get_case(case_id)
    finally:
        restarted.stop()

    assert persisted["assignee"] == "ops@epilabs.org"
    assert persisted["due_at"] == "2026-03-28"
    assert persisted["status"] == "resolved"
    assert len(persisted["comments"]) == 1


def test_worker_rebuild_preserves_latest_workflow_state_during_projection_race(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    touched = worker.store_items(
        [
            {
                "kind": "llm.request",
                "content": {"messages": [{"role": "user", "content": "Approve refund"}]},
                "meta": {"decision_id": "decision-race", "trace_id": "trace-race", "workflow_name": "Refund approvals"},
            },
            {
                "kind": "policy.check",
                "content": {"allowed": False, "rule_id": "RACE001", "summary": "Needs review"},
                "meta": {"decision_id": "decision-race", "trace_id": "trace-race", "workflow_name": "Refund approvals"},
            },
        ]
    )
    case_id = touched[0]

    stale_payload = worker.case_store._load_case_payload(case_id)  # noqa: SLF001 - targeted race regression
    assert stale_payload["status"] == "unassigned"

    updated = worker.update_case_workflow(
        case_id,
        {
            "status": "assigned",
            "assignee": "pilot@epilabs.org",
            "due_at": "2026-03-29",
            "updated_by": "lead@epilabs.org",
            "reason": "Race test triage",
        },
    )
    assert updated["status"] == "assigned"
    assert updated["assignee"] == "pilot@epilabs.org"
    assert updated["due_at"] == "2026-03-29"

    events = worker.case_store.list_events(case_id)
    stale_projection = worker.case_store._refresh_case_payload(  # noqa: SLF001 - targeted race regression
        case_id,
        build_case_payload_from_events(case_id, events, existing_payload=stale_payload),
        preserve_workflow_state=True,
    )
    assert stale_projection["status"] == "assigned"
    assert stale_projection["assignee"] == "pilot@epilabs.org"
    assert stale_projection["due_at"] == "2026-03-29"


def test_worker_snapshot_reports_replay_and_projection_state(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / "evidence_bad.json").write_text("{oops", encoding="utf-8")

    worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
    worker.start()
    try:
        snapshot = worker.snapshot()
    finally:
        worker.stop()

    assert snapshot["ready"] is True
    assert snapshot["corrupt_batch_count"] == 1
    assert snapshot["moved_corrupt_files"]
    assert snapshot["projection_failure_count"] == 0
