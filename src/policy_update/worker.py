"""Claim durable jobs, renew leases, and recover stalled processing.

Each processing transaction rechecks job ownership. Lapsed leases are requeued up
to ``max_attempts``, then require manual retry. Run embedded in the API or with
``python -m policy_update.worker``.
"""

import logging
import os
import signal
import socket
import threading
import uuid
from collections.abc import Callable
from contextlib import contextmanager

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, sessionmaker

from policy_update import service
from policy_update.agent import AgentRunner
from policy_update.extraction import ModelClient
from policy_update.models import ProcessingJob

log = logging.getLogger("policy_update.worker")

WAITING_STATUSES = {"awaiting_information", "awaiting_approval", "approved"}
RESUMABLE = {"awaiting_information", "approved"}


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class Worker:
    def __init__(
        self,
        sessions: sessionmaker,
        model: ModelClient | None,
        agent: AgentRunner | None,
        worker_id: str | None = None,
        lease_seconds: int = 90,
        poll_seconds: float = 1.0,
        max_attempts: int = 5,
    ):
        self.sessions = sessions
        self.model = model
        self.agent = agent
        self.id = worker_id or worker_identity()
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def sweep_stalled(self) -> list[str]:
        """Re-queue (or fail) every running job whose lease lapsed. Any worker may
        sweep; the compare-and-set inside makes concurrent sweeps harmless."""
        swept = []
        with self.sessions.begin() as session:
            stalled = service.stalled_jobs(session)
        # One transaction per job: the sweep never holds several case rows at once.
        for stale in stalled:
            with self.sessions.begin() as session:
                job = session.merge(stale, load=False)
                if service.requeue_stalled(session, job, self.max_attempts):
                    swept.append(job.case_id)
                    log.warning(
                        "job %s stalled (attempt %s): now %s", job.case_id, job.attempts, job.status
                    )
        return swept

    def queued(self) -> list[str]:
        with self.sessions.begin() as session:
            return list(
                session.scalars(
                    select(ProcessingJob.case_id)
                    .where(ProcessingJob.status == "queued")
                    .order_by(ProcessingJob.queued_at)
                )
            )

    def claim(self, case_id: str) -> bool:
        with self.sessions.begin() as session:
            return service.claim_job(session, case_id, self.id, self.lease_seconds)

    def run_pending(self, limit: int | None = None) -> list[str]:
        """One pass: sweep stalled jobs, then claim and run queued ones oldest first
        until the queue is empty (or ``limit`` jobs ran). Returns the case IDs run."""
        self.sweep_stalled()
        ran: list[str] = []
        while limit is None or len(ran) < limit:
            candidates = [case_id for case_id in self.queued() if case_id not in ran]
            if not candidates:
                break
            for case_id in candidates:
                if self.claim(case_id):
                    self.execute(case_id)
                    ran.append(case_id)
                    break
            else:
                break  # every candidate was claimed by someone else
        return ran

    def _owned(self, case_id: str) -> Callable[[Session], None]:
        # Lock order everywhere: the case row (get_case) first, then the job row.
        def guard(session: Session):
            service.owned_job(session, case_id, self.id)
            job = session.get(ProcessingJob, case_id)
            service.require_active(session, job.workspace_id)

        return guard

    @contextmanager
    def _heartbeat(self, case_id: str):
        """Renew the lease at a third of its length while the attempt runs."""
        done = threading.Event()

        def beat():
            while not done.wait(self.lease_seconds / 3):
                try:
                    with self.sessions.begin() as session:
                        renewed = service.renew_lease(session, case_id, self.id, self.lease_seconds)
                except Exception as error:
                    # A transient database error must not silently end the heartbeat.
                    log.warning("job %s: lease renewal failed (%s)", case_id, type(error).__name__)
                    continue
                if not renewed:
                    log.warning("job %s: lease lost during the attempt", case_id)
                    return

        thread = threading.Thread(target=beat, name=f"lease-{case_id[:8]}", daemon=True)
        thread.start()
        try:
            yield
        finally:
            done.set()
            thread.join()

    def execute(self, case_id: str) -> None:
        """Run the attempt for a job this worker has claimed. Every phase commits on
        its own; the case keeps its last committed state whatever happens here."""
        with self.sessions.begin() as session:
            job = session.get(ProcessingJob, case_id)
            workspace_id, action = job.workspace_id, job.action
        guard = self._owned(case_id)  # ownership is checked by the first step
        try:
            with self._heartbeat(case_id):
                self._attempt(case_id, workspace_id, action, guard)
            with self.sessions.begin() as session:
                case = service.get_case(session, workspace_id, case_id)
                status = "waiting" if case.status in WAITING_STATUSES else "completed"
                service.finish_job(session, case, self.id, status)
        except service.LeaseLost:
            # Another worker owns the case now; it will finish or fail the job.
            log.warning("job %s: taken over by another worker; stopping", case_id)
        except service.DomainError as error:
            # Model outages (503) are retryable; other refusals are recorded as-is so
            # the reviewer can see why the attempt could not proceed.
            self._fail(case_id, workspace_id, error.detail, error.status == 503)
        except Exception as error:
            # Exception class only: the message could carry request or document text.
            log.error("job %s: unexpected %s during processing", case_id, type(error).__name__)
            self._fail(case_id, workspace_id, "Unexpected processing error", True)

    def _attempt(self, case_id: str, workspace_id: str, requested: str, guard):
        """Run what the case needs *now*. ``requested`` is the action queued for the
        job, but a re-queued attempt may find the case further along (a run that
        died after committing its last step), so the step is derived from the case
        state; a case already waiting or finished has nothing left to run."""
        with self.sessions.begin() as session:
            case = service.get_case(session, workspace_id, case_id)
            guard(session)
            status = case.status
            if status == "received":
                action = "process"
                if self.agent is None:
                    service.process_case(session, case, self.model)
                    return
                service.begin_agent_processing(session, case, self.model)
            elif status == "processing" and self.agent is not None:
                action = "continue"
            elif status in RESUMABLE and requested == "resume" and self.agent is not None:
                # A resume whose first step failed has already consumed the interrupt;
                # its thread must be continued, not resumed again.
                action = self.agent.pending(case_id)
                if action == "resume":
                    event = service.resume_event(case)
                elif action is None:
                    log.info("job %s: no interrupted run to resume", case_id)
                    return
            else:
                log.info("job %s: case is %s; nothing left to run", case_id, status)
                return
        if action == "resume":
            self.agent.run(case_id, workspace_id, resume=event, guard=guard)
        else:
            self.agent.run(case_id, workspace_id, guard=guard)

    def _fail(self, case_id: str, workspace_id: str, detail: str, retryable: bool):
        try:
            with self.sessions.begin() as session:
                case = service.get_case(session, workspace_id, case_id)
                service.fail_job(session, case, self.id, detail, retryable)
        except service.LeaseLost:
            log.warning("job %s: failed after its lease was taken over", case_id)

    # ----- long-running ---------------------------------------------------------

    def run_forever(self, stop: threading.Event | None = None) -> None:
        stop = stop or self._stop
        log.info("worker %s polling every %ss", self.id, self.poll_seconds)
        while not stop.is_set():
            try:
                if self.run_pending():
                    continue  # drained something; look again without waiting
            except Exception as error:
                # Traceback/SQL parameters may include credentials or request text.
                log.error("worker %s: polling error (%s)", self.id, type(error).__name__)
            stop.wait(self.poll_seconds)

    def start(self) -> threading.Thread:
        """Embedded mode: run inside the current process on a daemon thread."""
        self._stop.clear()
        self._thread = threading.Thread(target=self.run_forever, name="policy-worker", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self, timeout: float = 30.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None


def main() -> None:
    """Separate worker process over the same database as the API."""
    from policy_update.runtime import build_runtime

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    runtime = build_runtime(worker_mode="external")
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    # Local mode waits for API initialization; verify mode has already checked the revision.
    while not stop.is_set() and not inspect(runtime.engine).has_table("processing_jobs"):
        log.info("waiting for the API to create the database schema")
        stop.wait(2)
    log.info(
        "extraction: %s; agent: %s",
        runtime.model.name if runtime.model else "unconfigured",
        runtime.agent.model.name if runtime.agent else "unconfigured",
    )
    runtime.worker.run_forever(stop)
    runtime.engine.dispose()


if __name__ == "__main__":
    main()
