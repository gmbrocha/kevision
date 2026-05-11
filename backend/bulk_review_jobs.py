from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .review_events import record_bulk_review_updates
from .review_queue import is_superseded
from .workspace import WorkspaceStore


RUNNING_STATES = {"queued", "running"}


class BulkReviewJobConflict(RuntimeError):
    pass


@dataclass
class BulkReviewJob:
    id: str
    project_id: str
    workspace_dir: str
    selected_change_ids: list[str]
    requested_status: str
    requested_action: str | None
    reviewer_id: str | None
    review_session_id: str | None
    state: str = "queued"
    total_selected: int = 0
    eligible_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    _done_event: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "workspace_dir": self.workspace_dir,
            "selected_change_ids": list(self.selected_change_ids),
            "requested_status": self.requested_status,
            "requested_action": self.requested_action,
            "reviewer_id": self.reviewer_id,
            "review_session_id": self.review_session_id,
            "state": self.state,
            "total_selected": self.total_selected,
            "eligible_count": self.eligible_count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class BulkReviewJobManager:
    def __init__(
        self,
        *,
        store_factory: Callable[[Path], WorkspaceStore] = WorkspaceStore,
        run_async: bool = True,
    ):
        self._store_factory = store_factory
        self._run_async = run_async
        self._lock = threading.RLock()
        self._jobs: dict[str, BulkReviewJob] = {}
        self._active_by_project: dict[str, str] = {}

    def start_job(
        self,
        *,
        project_id: str,
        workspace_dir: str | Path,
        selected_change_ids: list[str],
        requested_status: str,
        reviewer_id: str | None,
        review_session_id: str | None,
    ) -> BulkReviewJob:
        with self._lock:
            active = self.active_job(project_id)
            if active is not None:
                raise BulkReviewJobConflict(f"Bulk review is already running for project {project_id}.")
            job = BulkReviewJob(
                id=uuid.uuid4().hex,
                project_id=project_id,
                workspace_dir=str(Path(workspace_dir)),
                selected_change_ids=list(selected_change_ids),
                requested_status=requested_status,
                requested_action=_action_for_status(requested_status),
                reviewer_id=reviewer_id,
                review_session_id=review_session_id,
                total_selected=len(selected_change_ids),
                created_at=_utc_now(),
            )
            self._jobs[job.id] = job
            self._active_by_project[project_id] = job.id

        if self._run_async:
            thread = threading.Thread(target=self._run_job, args=(job.id,), daemon=True)
            thread.start()
        else:
            self._run_job(job.id)
        return self.get_job(job.id) or job

    def get_job(self, job_id: str) -> BulkReviewJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active_job(self, project_id: str) -> BulkReviewJob | None:
        with self._lock:
            job_id = self._active_by_project.get(project_id)
            if not job_id:
                return None
            job = self._jobs.get(job_id)
            if job is None or job.state not in RUNNING_STATES:
                self._active_by_project.pop(project_id, None)
                return None
            return job

    def has_running_job(self, project_id: str) -> bool:
        return self.active_job(project_id) is not None

    def status_payload(self, project_id: str, job_id: str | None = None) -> dict[str, object] | None:
        job = self.get_job(job_id) if job_id else self.active_job(project_id)
        if job is None or job.project_id != project_id:
            return None
        return job.to_dict()

    def wait(self, job_id: str, timeout: float = 10.0) -> bool:
        job = self.get_job(job_id)
        if job is None:
            return False
        return job._done_event.wait(timeout)

    def _run_job(self, job_id: str) -> None:
        self._set_state(job_id, state="running", started_at=_utc_now())
        try:
            job = self.get_job(job_id)
            if job is None:
                return
            store = self._store_factory(Path(job.workspace_dir)).load()
            item_changes, skipped_count = self._build_item_changes(store, job)
            self._update_counts(job_id, eligible_count=len(item_changes), skipped_count=skipped_count)
            result = record_bulk_review_updates(
                store,
                project_id=job.project_id,
                item_changes=item_changes,
                reviewer_id=job.reviewer_id,
                review_session_id=job.review_session_id,
                action=job.requested_action,
            )
            skipped_after_save = skipped_count + max(0, len(item_changes) - result.updated_count)
            self._set_state(
                job_id,
                state="done",
                updated_count=result.updated_count,
                skipped_count=skipped_after_save,
                finished_at=_utc_now(),
            )
        except Exception as exc:
            self._set_state(job_id, state="failed", error=str(exc), finished_at=_utc_now())
        finally:
            self._finish(job_id)

    def _build_item_changes(self, store: WorkspaceStore, job: BulkReviewJob) -> tuple[dict[str, dict[str, str]], int]:
        selected_once = list(dict.fromkeys(job.selected_change_ids))
        items_by_id = {item.id: item for item in store.data.change_items}
        item_changes: dict[str, dict[str, str]] = {}
        skipped_count = len(job.selected_change_ids) - len(selected_once)
        for change_id in selected_once:
            item = items_by_id.get(change_id)
            if item is None or is_superseded(item):
                skipped_count += 1
                continue
            reviewer_text = item.reviewer_text or item.raw_text
            if item.status == job.requested_status and item.reviewer_text == reviewer_text:
                skipped_count += 1
                continue
            item_changes[change_id] = {"status": job.requested_status, "reviewer_text": reviewer_text}
        return item_changes, skipped_count

    def _set_state(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)

    def _update_counts(self, job_id: str, *, eligible_count: int, skipped_count: int) -> None:
        self._set_state(job_id, eligible_count=eligible_count, skipped_count=skipped_count)

    def _finish(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if self._active_by_project.get(job.project_id) == job_id:
                self._active_by_project.pop(job.project_id, None)
            job._done_event.set()


def _action_for_status(status: str) -> str | None:
    if status == "approved":
        return "accept"
    if status == "rejected":
        return "reject"
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
