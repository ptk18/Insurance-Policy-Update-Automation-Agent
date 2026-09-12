import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from policy_update import service
from policy_update.agent import AgentRunner, make_checkpointer
from policy_update.database import initialize_database, make_database
from policy_update.extraction import ChatModel, ModelClient, model_from_env
from policy_update.fixtures import BROKERS, DOCUMENTS, EVIDENCE, SAMPLES, document_bytes
from policy_update.models import Case, ProcessingJob, Workspace
from policy_update.schemas import BrokerId, Intake, ProposalEdit, Rejection, Reply, VersionAction
from policy_update.settings import load_env_file

bearer = HTTPBearer(auto_error=False)
# Sentinel: "configure the model from the environment" as opposed to an explicit None.
FROM_ENV = object()


def session_dependency(request: Request):
    # Commit before returning success, including deferred constraint failures.
    with request.app.state.sessions.begin() as session:
        yield session


Db = Annotated[Session, Depends(session_dependency, scope="function")]


def workspace_dependency(
    session: Db,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Workspace:
    if credential is None:
        raise HTTPException(401, "A guest workspace bearer token is required")
    workspace = session.scalar(
        select(Workspace).where(Workspace.token_hash == service.token_hash(credential.credentials))
    )
    if workspace is None:
        raise HTTPException(401, "Invalid guest workspace token")
    return workspace


Guest = Annotated[Workspace, Depends(workspace_dependency)]


def owner_dependency(
    request: Request,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    # Agent routes must not hold a request-long transaction: each graph step opens
    # its own, so authenticate in a short one and return only the workspace ID.
    if credential is None:
        raise HTTPException(401, "A guest workspace bearer token is required")
    with request.app.state.sessions.begin() as session:
        workspace_id = session.scalar(
            select(Workspace.id).where(
                Workspace.token_hash == service.token_hash(credential.credentials)
            )
        )
    if workspace_id is None:
        raise HTTPException(401, "Invalid guest workspace token")
    return workspace_id


Owner = Annotated[str, Depends(owner_dependency)]


def file_response(content: bytes, content_type: str, filename: str) -> Response:
    return Response(
        content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def create_app(
    database_url: str | None = None,
    max_attachment_bytes: int | None = None,
    model: ModelClient | None | object = FROM_ENV,
    agent_model: ChatModel | None | object = FROM_ENV,
) -> FastAPI:
    """``model`` (extraction) and ``agent_model`` (tool selection) default to the
    provider configured through ``.env``/environment (``GEMINI_API_KEY``; set
    ``AGENT_LOOP=off`` to keep rule-based processing). Tests pass explicit fakes or
    ``None`` so no live call happens."""
    if model is FROM_ENV:
        load_env_file()
        model = model_from_env()
    if agent_model is FROM_ENV:
        enabled = os.environ.get("AGENT_LOOP", "on").lower() not in {"off", "0", "false"}
        agent_model = model if enabled and hasattr(model, "choose") else None
    database_url = database_url or os.environ.get("DATABASE_URL", "sqlite:///./policy_demo.db")
    engine, sessions = make_database(database_url)
    agent = (
        AgentRunner(
            agent_model,
            make_checkpointer(database_url),
            sessions,
            budget=int(os.environ.get("AGENT_TOOL_BUDGET", "12")),
        )
        if agent_model is not None
        else None
    )
    attachment_limit = max_attachment_bytes or int(
        os.environ.get("MAX_ATTACHMENT_BYTES", str(5 * 1024 * 1024))
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="Insurance Policy Update — backend foundation",
        version="0.1.0",
        description="Synthetic-data review API. Structured or free-text intake, uploaded "
        "PDF evidence, and text-only hosted-model extraction; image inspection, the "
        "agent worker, and the dashboard are not implemented yet.",
        lifespan=lifespan,
    )
    app.state.sessions = sessions
    app.state.engine = engine
    app.state.model = model
    app.state.agent = agent

    @app.exception_handler(service.DomainError)
    async def domain_error(_request, error):
        return JSONResponse(status_code=error.status, content={"detail": error.detail})

    @app.exception_handler(StaleDataError)
    @app.exception_handler(IntegrityError)
    async def conflicting_write(_request, _error):
        return JSONResponse(
            status_code=409,
            content={"detail": "A concurrent operation changed this record; reload and retry"},
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request, error):
        # Do not reflect raw email/document input or submitted credentials in errors.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
                    for item in error.errors()
                ]
            },
        )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "extraction": model.name if model else "unconfigured",
            "agent": agent.model.name if agent else "unconfigured",
        }

    @app.post("/workspaces", status_code=201)
    def new_workspace(session: Db):
        workspace, token = service.create_workspace(session)
        return {"workspace_id": workspace.id, "token": token, "token_type": "bearer"}

    @app.get("/fixtures")
    def fixtures(_guest: Guest):
        documents = [
            {
                "id": document_id,
                **metadata,
                "size": len(document_bytes(document_id)),
                "download": f"/fixtures/documents/{document_id}",
            }
            for document_id, metadata in DOCUMENTS.items()
        ]
        return {
            "brokers": BROKERS,
            "evidence": EVIDENCE,
            "documents": documents,
            "samples": SAMPLES,
        }

    @app.get("/fixtures/documents/{document_id}")
    def fixture_document(document_id: str, _guest: Guest):
        if document_id not in DOCUMENTS:
            raise HTTPException(404, "Sample document not found")
        metadata = DOCUMENTS[document_id]
        return file_response(
            document_bytes(document_id), metadata["content_type"], metadata["filename"]
        )

    @app.get("/policies/{number}")
    def policy(number: str, broker_id: BrokerId, session: Db, guest: Guest):
        return service.policy_view(service.get_policy(session, guest.id, number, broker_id))

    @app.post("/cases", status_code=201)
    def intake(data: Intake, session: Db, guest: Guest):
        # Persist only. Processing runs in its own transaction via /cases/{id}/process.
        case = service.create_case(session, guest.id, data)
        return service.case_view(session, case)

    def record_failure(case_id: str, owner: str, detail: str, retryable: bool):
        with sessions.begin() as session:
            service.fail_job(session, service.get_case(session, owner, case_id), detail, retryable)

    def attempt(case_id: str, owner: str, allowed: set[str], retry: bool = False):
        """One processing attempt wrapped in a durable job record. Each phase commits
        on its own so a failure inside the run is recorded even though the case
        itself keeps its last committed state and stays retryable."""
        with sessions.begin() as session:
            case = service.get_case(session, owner, case_id)
            action = service.next_action(case, agent is not None)
            if action not in allowed:
                raise service.DomainError(409, f"Use /retry to {action} this case")
            service.start_job(session, case, action, retry)
        try:
            if agent is None:
                with sessions.begin() as session:
                    case = service.get_case(session, owner, case_id)
                    service.process_case(session, case, model)
            elif action == "process":
                with sessions.begin() as session:
                    case = service.get_case(session, owner, case_id)
                    service.begin_agent_processing(session, case, model)
                agent.run(case_id, owner)
            elif action == "continue":
                agent.run(case_id, owner)
            else:
                with sessions.begin() as session:
                    event = service.resume_event(service.get_case(session, owner, case_id))
                agent.run(case_id, owner, resume=event)
        except service.DomainError as error:
            # 409s are precondition refusals (concurrent run, state changed), not a
            # failed attempt; anything else is recorded on the job for manual retry.
            if error.status != 409:
                record_failure(case_id, owner, error.detail, error.status == 503)
            raise
        except Exception:
            # An unexpected crash inside the attempt: the case keeps its last committed
            # state; mark the job failed so it is visible and can be retried.
            record_failure(case_id, owner, "Unexpected processing error", True)
            raise
        with sessions.begin() as session:
            case = service.get_case(session, owner, case_id)
            waiting = case.status in {"awaiting_information", "awaiting_approval", "approved"}
            service.finish_job(session, case, "waiting" if waiting else "completed")
            return service.case_view(session, case)

    @app.post("/cases/{case_id}/process")
    def process(case_id: str, owner: Owner):
        # Rule-based when no model is configured; otherwise the agent loop. A case
        # left `processing` by a failure continues from its checkpoint.
        return attempt(case_id, owner, {"process", "continue"})

    @app.post("/cases/{case_id}/resume")
    def resume(case_id: str, owner: Owner):
        # Continue the agent after a human reply or approval. Approval itself stays a
        # reviewer API action; the loop only observes its result.
        if agent is None:
            raise HTTPException(409, "No agent loop is configured; use /execute instead")
        return attempt(case_id, owner, {"resume"})

    @app.post("/cases/{case_id}/retry")
    def retry(case_id: str, owner: Owner):
        # Manual recovery for a failed or stalled job: runs whichever attempt applies.
        return attempt(case_id, owner, {"process", "continue", "resume"}, retry=True)

    @app.post("/cases/{case_id}/attachments", status_code=201)
    def upload(case_id: str, file: Annotated[UploadFile, File()], session: Db, guest: Guest):
        case = service.get_case(session, guest.id, case_id)
        # Read at most one byte past the limit so an oversized body is never buffered.
        content = file.file.read(attachment_limit + 1)
        attachment = service.store_attachment(
            session, case, file.filename, content, attachment_limit
        )
        return service.attachment_view(attachment)

    @app.get("/cases/{case_id}/attachments/{attachment_id}")
    def attachment_detail(case_id: str, attachment_id: str, session: Db, guest: Guest):
        case = service.get_case(session, guest.id, case_id)
        return service.attachment_view(service.get_attachment(session, case, attachment_id))

    @app.get("/cases/{case_id}/attachments/{attachment_id}/content")
    def attachment_content(case_id: str, attachment_id: str, session: Db, guest: Guest):
        case = service.get_case(session, guest.id, case_id)
        attachment = service.get_attachment(session, case, attachment_id)
        return file_response(attachment.content, attachment.content_type, attachment.filename)

    @app.get("/cases")
    def cases(session: Db, guest: Guest):
        rows = session.scalars(
            select(Case).where(Case.workspace_id == guest.id).order_by(Case.created_at.desc())
        ).all()
        return [
            {
                "id": row.id,
                "status": row.status,
                "job_status": job.status if (job := session.get(ProcessingJob, row.id)) else None,
                "policy_number": row.policy_number,
                "broker_id": row.broker_id,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    @app.get("/cases/{case_id}")
    def case_detail(case_id: str, session: Db, guest: Guest):
        return service.case_view(session, service.get_case(session, guest.id, case_id))

    @app.put("/cases/{case_id}/proposal")
    def edit(case_id: str, data: ProposalEdit, session: Db, guest: Guest):
        case = service.get_case(session, guest.id, case_id)
        service.edit_proposal(session, case, data)
        return service.case_view(session, case)

    @app.post("/cases/{case_id}/replies")
    def reply(case_id: str, data: Reply, session: Db, guest: Guest):
        case = service.get_case(session, guest.id, case_id)
        service.add_reply(session, case, data)
        return service.case_view(session, case)

    @app.post("/cases/{case_id}/approve")
    def approve(case_id: str, data: VersionAction, session: Db, guest: Guest):
        case = service.get_case(session, guest.id, case_id)
        service.approve(session, case, data.version)
        return service.case_view(session, case)

    @app.post("/cases/{case_id}/reject")
    def reject(case_id: str, data: Rejection, session: Db, guest: Guest):
        case = service.get_case(session, guest.id, case_id)
        service.reject(session, case, data.version, data.reason)
        return service.case_view(session, case)

    @app.post("/cases/{case_id}/execute")
    def execute(case_id: str, data: VersionAction, session: Db, guest: Guest):
        case = service.get_case(session, guest.id, case_id)
        return service.apply_approved_update(session, case, data.version)

    return app
