"""Isolated browser-test API. Never loads .env or calls a hosted model."""

from tempfile import TemporaryDirectory

import uvicorn

from policy_update.api import create_app
from policy_update.extraction import ModelError, ModelResponse


class ScriptedExtraction:
    """One known retry scenario; all other free-text calls fail loudly."""

    name = "fake:browser-tests"

    def __init__(self):
        self.attempts = 0

    def extract(self, text, context=None):
        assert text == "RETRY-SCENARIO: DEMO-1001 email to retry@example.com"
        self.attempts += 1
        if self.attempts % 2 == 1:
            raise ModelError("Model request returned HTTP 429 RESOURCE_EXHAUSTED", True)
        return ModelResponse(
            data={
                "policy_number": "DEMO-1001",
                "mailing_address": None,
                "email": "retry@example.com",
                "phone": None,
                "unsupported_requests": [],
                "ambiguities": [],
            }
        )


if __name__ == "__main__":
    with TemporaryDirectory(prefix="policy-dashboard-test-") as directory:
        app = create_app(
            database_url=f"sqlite:///{directory}/browser.db",
            model=ScriptedExtraction(),
            agent_model=None,
            worker_mode="embedded",
        )
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
