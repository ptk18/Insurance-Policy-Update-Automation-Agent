"""Run the synthetic review workflow against the local API without printing credentials."""

import json
import secrets
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8000"


def multipart(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----demo" + secrets.token_hex(8)
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def main():
    token = None

    def request(method, path, data=None, raw=None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if raw is not None:
            body, headers["Content-Type"] = raw
        else:
            body = json.dumps(data).encode() if data is not None else None
            headers["Content-Type"] = "application/json"
        req = Request(BASE_URL + path, data=body, headers=headers, method=method)
        with urlopen(req, timeout=180) as response:
            if response.headers.get_content_type() == "application/json":
                return json.load(response)
            return response.read()

    def upload(path, document_id):
        content = request("GET", f"/fixtures/documents/{document_id}")
        return request("POST", path + "/attachments", raw=multipart(f"{document_id}.pdf", content))

    token = request("POST", "/workspaces")["token"]
    health = request("GET", "/health")
    agent = health["agent"] != "unconfigured"
    print(f"extraction: {health['extraction']}; agent loop: {health['agent']}")

    def tools_used(case):
        calls = [e["details"]["tool"] for e in case["timeline"] if e["action"] == "tool_called"]
        return " -> ".join(calls) if calls else "rule-based processing"

    def complete(path, case):
        # Approval is always the reviewer's call; the agent only applies it afterwards.
        version = {"version": case["current_version"]}
        request("POST", path + "/approve", version)
        if agent:
            case = request("POST", path + "/resume")
            print(f"  agent resumed after approval: {case['status']} ({tools_used(case)})")
        receipt = request("POST", path + "/execute", version)
        repeated = request("POST", path + "/execute", version)
        if repeated != receipt:
            raise RuntimeError("Retry returned a different execution outcome")
        return request("GET", path)

    def process(path):
        # A hosted-model 503/502 leaves the case `processing` with its checkpoint;
        # calling /process again continues from the last completed step.
        for attempt in range(4):
            try:
                return request("POST", path + "/process")
            except HTTPError as error:
                if error.code not in (502, 503) or attempt == 3:
                    raise
                print(f"  model unavailable (HTTP {error.code}); retrying processing")
                time.sleep(8)

    samples = request("GET", "/fixtures")["samples"]
    for sample in (samples[0], samples[2], samples[3]):
        received = request("POST", "/cases", sample["intake"])
        path = f"/cases/{received['id']}"
        case = process(path)
        print(f"{sample['title']}: {received['status']} -> {case['status']} ({tools_used(case)})")
        if case["status"] == "awaiting_information":
            try:
                request("POST", path + "/approve", {"version": case["current_version"]})
            except HTTPError as error:
                if error.code != 409:
                    raise
                print("  Approval blocked while evidence is unresolved.")
            else:
                raise RuntimeError("Unresolved evidence was incorrectly approved")
            case = request(
                "POST",
                path + "/replies",
                {
                    "expected_version": case["current_version"],
                    "text": "Here is the corrected fictional proof of address.",
                    "evidence_id": "matching-address",
                },
            )
            print(f"  Corrected evidence: {case['status']}")
        if case["status"] != "awaiting_approval":
            print(f"  Left for human review: {case['proposals'][-1]['findings']}")
            continue
        completed = complete(path, case)
        print(f"  {completed['status']}; duplicate execution returned the saved result.")
        print(f"  {completed['confirmation_draft']}")

    # Fourth scenario: a real (fictional) PDF upload that conflicts, then a corrected upload.
    case = request("POST", "/cases", samples[1]["intake"] | {"evidence_id": None})
    path = f"/cases/{case['id']}"
    upload(path, "conflicting-pdf")
    case = process(path)
    print(f"Uploaded conflicting PDF: {case['status']}")
    corrected = upload(path, "matching-pdf")
    print(f"  Inspected corrected PDF: page {corrected['inspection']['source']['page']}")
    case = request(
        "POST",
        path + "/replies",
        {
            "expected_version": case["current_version"],
            "text": "Corrected statement uploaded.",
            "evidence_id": corrected["id"],
        },
    )
    print(f"  Corrected upload bound by reply: {case['status']}")
    if case["status"] == "awaiting_approval":
        print(f"  {complete(path, case)['status']} with uploaded-document evidence.")
    else:
        print(f"  Left for human review: {case['proposals'][-1]['findings']}")
    # Fifth scenario: free-text intake extracted by the hosted model, when configured.
    extraction = request("GET", "/health")["extraction"]
    if extraction == "unconfigured":
        print("Skipped free-text extraction: no GEMINI_API_KEY configured on the server.")
        print("All four synthetic scenarios finished. No email was sent.")
        return
    for sample in (samples[4], samples[5]):
        case = request("POST", "/cases", sample["intake"])
        path = f"/cases/{case['id']}"
        case = process(path)
        print(f"{sample['title']} via {extraction}: {case['status']} ({tools_used(case)})")
        findings = case["proposals"][-1]["findings"]
        print(f"  extracted changes: {case['requested_changes']}; policy {case['policy_number']}")
        if case["status"] != "awaiting_approval":
            print("  " + "; ".join(finding["code"] for finding in findings))
            print(f"  {case['follow_up_draft']}")
            continue
        print(f"  {complete(path, case)['status']} after human approval.")
    print("All synthetic scenarios finished. No email was sent.")


if __name__ == "__main__":
    main()
