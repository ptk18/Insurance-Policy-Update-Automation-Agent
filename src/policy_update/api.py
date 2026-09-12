import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from policy_update import service
from policy_update.database import initialize_database, make_database
from policy_update.fixtures import BROKERS, EVIDENCE, SAMPLES
from policy_update.models import Case, Workspace
from policy_update.schemas import BrokerId, Intake, ProposalEdit, Rejection, Reply, VersionAction

bearer = HTTPBearer(auto_error=False)


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


def create_app(database_url: str | None = None) -> FastAPI:
    engine, sessions = make_database(
        database_url or os.environ.get("DATABASE_URL", "sqlite:///./policy_demo.db")
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="Insurance Policy Update — backend foundation",
        version="0.1.0",
        description="Synthetic-data review API. Structured inputs and fixture evidence; "
        "LLM processing, file uploads, and the dashboard are not implemented yet.",
        lifespan=lifespan,
    )
    app.state.sessions = sessions
    app.state.engine = engine

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
        return {"status": "ok"}

    @app.post("/workspaces", status_code=201)
    def new_workspace(session: Db):
        workspace, token = service.create_workspace(session)
        return {"workspace_id": workspace.id, "token": token, "token_type": "bearer"}

    @app.get("/fixtures")
    def fixtures(_guest: Guest):
        return {"brokers": BROKERS, "evidence": EVIDENCE, "samples": SAMPLES}

    @app.get("/policies/{number}")
    def policy(number: str, broker_id: BrokerId, session: Db, guest: Guest):
        return service.policy_view(service.get_policy(session, guest.id, number, broker_id))

    @app.post("/cases", status_code=201)
    def intake(data: Intake, session: Db, guest: Guest):
        case = service.create_case(session, guest.id, data)
        return service.case_view(session, case)

    @app.get("/cases")
    def cases(session: Db, guest: Guest):
        rows = session.scalars(
            select(Case).where(Case.workspace_id == guest.id).order_by(Case.created_at.desc())
        ).all()
        return [
            {
                "id": row.id,
                "status": row.status,
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
