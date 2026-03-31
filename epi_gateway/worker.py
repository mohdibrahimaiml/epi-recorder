import json
import logging
from pathlib import Path
import queue
import threading
import time
from typing import Any, Callable

from epi_core.capture import CaptureBatchModel, CaptureEventModel, build_capture_batch, coerce_capture_event
from epi_core.case_store import CaseStore, ReplaySpoolResultModel
from epi_core.time_utils import utc_now_iso

logger = logging.getLogger("epi-gateway.worker")


class EvidenceWorker:
    """
    Background worker that spools accepted events and projects them into cases.

    v1 is optimized for a single-node self-hosted deployment:
    - append-only JSON event batches on disk
    - SQLite case store for the shared reviewer inbox
    - replay on startup for recovery
    """

    def __init__(
        self,
        storage_dir: str | Path = "./evidence_vault",
        *,
        batch_size: int = 50,
        batch_timeout: float = 2.0,
    ):
        self._queue: queue.Queue[Any] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self.storage_path = Path(storage_dir)
        self.events_path = self.storage_path / "events"
        self.db_path = self.storage_path / "cases.sqlite3"
        self.case_store = CaseStore(self.db_path)

        self.processed_count = 0
        self.replayed_batches = 0
        self.replay_result = ReplaySpoolResultModel()
        self.ready = False
        self.last_start_error: str | None = None
        self._post_persist_hook: Callable[[list[CaptureEventModel], "EvidenceWorker"], None] | None = None

        self.batch_size = max(1, int(batch_size))
        self.batch_timeout = max(0.1, float(batch_timeout))

        self.events_path.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        """Replay any unapplied spool batches and start the background thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self.ready = False
        self.last_start_error = None
        self.events_path.mkdir(parents=True, exist_ok=True)
        try:
            self.replay_result = self.case_store.replay_spool(self.events_path)
            self.replayed_batches += self.replay_result.applied_batches
            self._recover_orphan_sessions()
        except Exception as exc:
            self.last_start_error = str(exc)
            logger.error("Gateway worker failed during startup replay: %s", exc, exc_info=True)
            raise

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="EPI-GatewayWorker",
        )
        self._thread.start()
        self.ready = True
        logger.info("Gateway worker started")

    def stop(self) -> None:
        """Signal the worker to stop and wait for it."""
        logger.info("Stopping gateway worker")
        self.ready = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10.0)
        logger.info("Gateway worker stopped")

    def enqueue(self, item: dict[str, Any]) -> None:
        """Queue one capture event for background persistence."""
        self._queue.put(coerce_capture_event(item))

    def set_post_persist_hook(
        self,
        hook: Callable[[list[CaptureEventModel], "EvidenceWorker"], None] | None,
    ) -> None:
        self._post_persist_hook = hook

    def store_items(self, items: list[dict[str, Any] | Any]) -> list[str]:
        """Synchronously persist items to the spool and project them into cases."""
        if not items:
            return []
        batch = build_capture_batch(items)
        return self._persist_batch(batch)

    def upsert_case_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Compatibility path for older browser flows posting full cases."""
        return self.case_store.upsert_case_payload(payload)

    def sync_auth_users(self, users: list[dict[str, Any]], *, source: str | None = None) -> int:
        return self.case_store.sync_auth_users(users, source=source)

    def list_auth_users(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.case_store.list_auth_users()]

    def authenticate_user(self, username: str, password: str):
        return self.case_store.authenticate_user(username, password)

    def create_auth_session(self, user, *, ttl_hours: float = 12.0):
        return self.case_store.create_auth_session(user, ttl_hours=ttl_hours)

    def get_auth_session(self, token: str):
        return self.case_store.get_auth_session(token)

    def revoke_auth_session(self, token: str) -> None:
        self.case_store.revoke_auth_session(token)

    def list_cases(
        self,
        *,
        status: str | None = None,
        trust: str | None = None,
        review: str | None = None,
        workflow: str | None = None,
        search: str | None = None,
        assignee: str | None = None,
        overdue: bool | None = None,
    ) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in self.case_store.list_cases(
                status=status,
                trust=trust,
                review=review,
                workflow=workflow,
                search=search,
                assignee=assignee,
                overdue=overdue,
            )
        ]

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        return self.case_store.get_case(case_id)

    def find_case_id_for_workflow(self, workflow_id: str) -> str | None:
        return self.case_store.find_case_id_for_workflow(workflow_id)

    def find_approval_request(self, workflow_id: str, approval_id: str) -> dict[str, Any] | None:
        return self.case_store.find_approval_request(workflow_id, approval_id)

    def save_review(self, case_id: str, review_payload: dict[str, Any]) -> dict[str, Any]:
        return self.case_store.save_review(case_id, review_payload)

    def update_case_workflow(self, case_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        return self.case_store.update_case_workflow(case_id, updates)

    def list_comments(self, case_id: str) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.case_store.list_comments(case_id)]

    def add_comment(self, case_id: str, author: str, body: str, *, created_at: str | None = None) -> dict[str, Any]:
        return self.case_store.add_comment(case_id, author, body, created_at=created_at)

    def record_system_activity(
        self,
        case_id: str,
        *,
        kind: str,
        title: str,
        copy: str,
        actor: str = "epi-gateway",
        created_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.case_store.record_system_activity(
            case_id,
            kind=kind,
            title=title,
            copy=copy,
            actor=actor,
            created_at=created_at,
            metadata=metadata,
        )

    def export_case(
        self,
        case_id: str,
        output_path: Path,
        *,
        signer_function: Any | None = None,
    ):
        return self.case_store.export_case_to_artifact(
            case_id,
            output_path,
            signer_function=signer_function,
        )

    def queue_size(self) -> int:
        return self._queue.qsize()

    def snapshot(self) -> dict[str, Any]:
        case_count = len(self.case_store.list_cases())
        return {
            "ready": self.ready,
            "queue_size": self.queue_size(),
            "processed_count": self.processed_count,
            "storage_dir": str(self.storage_path),
            "events_dir": str(self.events_path),
            "database_path": str(self.db_path),
            "batch_size": self.batch_size,
            "batch_timeout": self.batch_timeout,
            "replayed_batches": self.replayed_batches,
            "skipped_replay_batches": self.replay_result.skipped_batches,
            "corrupt_batch_count": self.replay_result.corrupt_batch_count,
            "corrupt_files": list(self.replay_result.corrupt_files),
            "moved_corrupt_files": list(self.replay_result.moved_corrupt_files),
            "replay_last_error": self.replay_result.last_error,
            "last_start_error": self.last_start_error,
            "projection_failure_count": self.case_store.projection_failure_count,
            "last_projection_error": self.case_store.last_projection_error,
            "case_count": case_count,
            "auth_user_count": len(self.case_store.list_auth_users()),
        }

    def _run_loop(self) -> None:
        """Main processing loop with a simple batch strategy."""
        buffer: list[Any] = []
        last_flush_time = time.time()

        while not self._stop_event.is_set():
            try:
                try:
                    item = self._queue.get(timeout=1.0)
                    buffer.append(item)
                    self._queue.task_done()
                except queue.Empty:
                    pass

                if not buffer:
                    last_flush_time = time.time()

                if len(buffer) >= self.batch_size:
                    self._flush_batch(buffer)
                    buffer = []
                    last_flush_time = time.time()
                elif buffer and (time.time() - last_flush_time > self.batch_timeout):
                    logger.info("Batch timeout reached; flushing buffered events")
                    self._flush_batch(buffer)
                    buffer = []
                    last_flush_time = time.time()
            except Exception as exc:
                logger.error("Critical worker loop error: %s", exc, exc_info=True)

        if buffer:
            logger.info("Shutdown detected; flushing remaining events")
            self._flush_batch(buffer)

    def _flush_batch(self, buffer: list[Any]) -> None:
        if not buffer:
            return

        batch = build_capture_batch(buffer)
        self._persist_batch(batch)

    def _persist_batch(self, batch: CaptureBatchModel) -> list[str]:
        model = CaptureBatchModel.model_validate(batch)
        payload = model.model_dump(mode="json")
        payload["_signed_batch"] = True

        file_path = self.events_path / f"evidence_{model.batch_id}.json"
        with file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)

        touched_case_ids = self.case_store.apply_batch(payload, file_name=file_path.name)
        self.processed_count += len(model.items)
        logger.info(
            "Persisted batch %s with %s item(s); touched %s case(s)",
            model.batch_id,
            len(model.items),
            len(touched_case_ids),
        )
        if self._post_persist_hook:
            try:
                self._post_persist_hook(list(model.items), self)
            except Exception as exc:
                logger.warning("Post-persist hook failed: %s", exc, exc_info=True)
        return touched_case_ids

    def _recover_orphan_sessions(self) -> None:
        for session in self.case_store.list_open_sessions():
            logger.warning("Recovering orphan workflow session: %s", session.workflow_id)
            touched_case_ids = self.store_items(
                [
                    {
                        "case_id": session.case_id,
                        "workflow_id": session.workflow_id,
                        "kind": "agent.run.recovered",
                        "captured_at": utc_now_iso(),
                        "content": {
                            "reason": "Gateway restarted before the run logged a clean completion event.",
                            "recovered_at": utc_now_iso(),
                            "started_at": session.started_at,
                            "last_event_at": session.last_event_at,
                        },
                    }
                ]
            )
            case_id = session.case_id or (touched_case_ids[0] if touched_case_ids else None)
            if case_id:
                try:
                    self.record_system_activity(
                        case_id,
                        kind="session_recovered",
                        title="Run recovered after gateway restart",
                        copy="EPI recovered this run because the gateway restarted before a clean run end was captured.",
                        created_at=utc_now_iso(),
                        metadata={
                            "workflow_id": session.workflow_id,
                            "started_at": session.started_at,
                            "last_event_at": session.last_event_at,
                        },
                    )
                except KeyError:
                    logger.warning("Recovered workflow %s did not resolve to a persisted case", session.workflow_id)
            self.case_store.delete_open_session(session.workflow_id)
