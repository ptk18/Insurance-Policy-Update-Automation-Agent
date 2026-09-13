"""The processing stack shared by the API process and a separate worker process:
database sessions, the configured models, the agent runner, and the worker that
claims jobs. Both entry points build it the same way from ``.env``/environment."""

import os
from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from policy_update.agent import AgentRunner, make_checkpointer
from policy_update.database import make_database
from policy_update.extraction import ChatModel, ModelClient, model_from_env
from policy_update.settings import load_env_file
from policy_update.worker import Worker

# Sentinel: "configure the model from the environment" as opposed to an explicit None.
FROM_ENV = object()
WORKER_MODES = {"embedded", "external"}


@dataclass
class Runtime:
    database_url: str
    engine: object
    sessions: sessionmaker
    model: ModelClient | None
    agent: AgentRunner | None
    worker: Worker
    # ``embedded``: the API process runs a worker thread; ``external``: only
    # ``python -m policy_update.worker`` processes claim jobs.
    worker_mode: str


def build_runtime(
    database_url: str | None = None,
    model: ModelClient | None | object = FROM_ENV,
    agent_model: ChatModel | None | object = FROM_ENV,
    worker_mode: str | None = None,
) -> Runtime:
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
    worker = Worker(
        sessions,
        model,
        agent,
        lease_seconds=int(os.environ.get("JOB_LEASE_SECONDS", "90")),
        poll_seconds=float(os.environ.get("WORKER_POLL_SECONDS", "1")),
        max_attempts=int(os.environ.get("MAX_JOB_ATTEMPTS", "5")),
    )
    worker_mode = worker_mode or os.environ.get("WORKER_MODE", "embedded").lower()
    if worker_mode not in WORKER_MODES:
        raise ValueError(f"WORKER_MODE must be one of {sorted(WORKER_MODES)}")
    return Runtime(database_url, engine, sessions, model, agent, worker, worker_mode)
