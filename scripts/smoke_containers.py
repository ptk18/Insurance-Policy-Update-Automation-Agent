"""Smoke the isolated, model-free Compose stack, optionally restarting its services.

Start it with: GEMINI_API_KEY= docker compose --env-file /dev/null -p policy-verify up -d
No token is written to disk or printed. Never use this against a hosted/live-model API.
"""

import argparse
import subprocess
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:3003"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--project", default="policy-verify", help="Compose project to restart")
    args = parser.parse_args()
    with httpx.Client(base_url=BASE, headers={"Origin": BASE}, timeout=30) as client:
        health = client.get("/api/backend/health").json()
        assert health["agent"] == health["extraction"] == "unconfigured", "Refusing live model"
        assert health["worker"] == "external"
        client.post("/api/session").raise_for_status()

        def api(method, path, **kwargs):
            response = client.request(method, "/api/backend" + path, **kwargs)
            response.raise_for_status()
            return response.json()

        def wait(case_id):
            for _ in range(60):
                record = api("GET", f"/cases/{case_id}")
                if record["job"]["status"] not in {"queued", "running"}:
                    return record
                time.sleep(0.25)
            raise AssertionError("Worker did not finish the synthetic job")

        data = {
            "broker_id": "broker-alex",
            "policy_number": "DEMO-1001",
            "original_request": "Update DEMO-1001 email to container@example.com",
            "changes": {"email": "container@example.com"},
        }
        case = api("POST", "/cases", json=data)
        path = f"/cases/{case['id']}"
        api("POST", path + "/process")
        assert wait(case["id"])["status"] == "awaiting_approval"
        denied = client.post("/api/backend" + path + "/execute", json={"version": 1})
        assert denied.status_code == 409
        api("POST", path + "/approve", json={"version": 1})
        receipt = api("POST", path + "/execute", json={"version": 1})

        data["changes"] = {"mailing_address": "42 Orchard Lane, Demo City, 10001"}
        missing = api("POST", "/cases", json=data)
        missing_path = f"/cases/{missing['id']}"
        api("POST", missing_path + "/process")
        assert wait(missing["id"])["status"] == "awaiting_information"

        if args.restart:
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    "/dev/null",
                    "-p",
                    args.project,
                    "restart",
                    "db",
                    "api",
                    "worker",
                    "frontend",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            for _ in range(60):
                try:
                    response = client.get("/api/backend/health")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                raise AssertionError("Stack did not recover after restart")

        assert api("POST", path + "/execute", json={"version": 1}) == receipt
        record = api("GET", path)
        assert record["status"] == "completed"
        assert sum(e["action"] == "update_applied" for e in record["timeline"]) == 1
        assert api("GET", missing_path)["status"] == "awaiting_information"
        pdf = Path(__file__).resolve().parents[1] / "src/policy_update/assets/proof-matching.pdf"
        attachment = api(
            "POST",
            missing_path + "/attachments",
            files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")},
        )
        record = api(
            "POST",
            missing_path + "/replies",
            json={
                "expected_version": 1,
                "text": "Corrected proof attached",
                "evidence_id": attachment["id"],
            },
        )
        assert record["status"] == "awaiting_approval" and record["current_version"] == 2
        api("POST", missing_path + "/approve", json={"version": 2})
        api("POST", missing_path + "/execute", json={"version": 2})
        assert api("GET", missing_path)["status"] == "completed"
        with httpx.Client(base_url=BASE, headers={"Origin": BASE}) as other:
            other.post("/api/session").raise_for_status()
            assert other.get("/api/backend" + path).status_code == 404
            assert (
                other.get(
                    f"/api/backend{missing_path}/attachments/{attachment['id']}/content"
                ).status_code
                == 404
            )
    print(
        "Container smoke passed: worker, approval, replay, PDF correction, isolation"
        + (", and full-stack restart" if args.restart else "")
    )


if __name__ == "__main__":
    main()
