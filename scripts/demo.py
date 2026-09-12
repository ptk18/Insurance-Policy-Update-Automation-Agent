"""Run the synthetic review workflow against the local API without printing credentials."""

import json
import secrets
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
        with urlopen(req, timeout=15) as response:
            if response.headers.get_content_type() == "application/json":
                return json.load(response)
            return response.read()

    def upload(path, document_id):
        content = request("GET", f"/fixtures/documents/{document_id}")
        return request("POST", path + "/attachments", raw=multipart(f"{document_id}.pdf", content))

    token = request("POST", "/workspaces")["token"]
    samples = request("GET", "/fixtures")["samples"]
    for sample in (samples[0], samples[2], samples[3]):
        received = request("POST", "/cases", sample["intake"])
        path = f"/cases/{received['id']}"
        case = request("POST", path + "/process")
        print(f"{sample['title']}: {received['status']} -> {case['status']}")
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
        version = {"version": case["current_version"]}
        request("POST", path + "/approve", version)
        receipt = request("POST", path + "/execute", version)
        repeated = request("POST", path + "/execute", version)
        if repeated != receipt:
            raise RuntimeError("Retry returned a different execution outcome")
        completed = request("GET", path)
        print(f"  {completed['status']}; duplicate execution returned the saved result.")
        print(f"  {completed['confirmation_draft']}")

    # Fourth scenario: a real (fictional) PDF upload that conflicts, then a corrected upload.
    case = request("POST", "/cases", samples[1]["intake"] | {"evidence_id": None})
    path = f"/cases/{case['id']}"
    upload(path, "conflicting-pdf")
    case = request("POST", path + "/process")
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
    version = {"version": case["current_version"]}
    request("POST", path + "/approve", version)
    request("POST", path + "/execute", version)
    print(f"  {request('GET', path)['status']} with uploaded-document evidence.")
    print("All four synthetic scenarios finished. No email was sent.")


if __name__ == "__main__":
    main()
