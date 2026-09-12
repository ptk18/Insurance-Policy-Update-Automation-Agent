"""Run the synthetic review workflow against the local API without printing credentials."""

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8000"


def main():
    token = None

    def request(method, path, data=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = Request(
            BASE_URL + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
            method=method,
        )
        with urlopen(req, timeout=15) as response:
            return json.load(response)

    token = request("POST", "/workspaces")["token"]
    samples = request("GET", "/fixtures")["samples"]
    for sample in (samples[0], samples[2], samples[3]):
        case = request("POST", "/cases", sample["intake"])
        path = f"/cases/{case['id']}"
        print(f"{sample['title']}: {case['status']}")
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
    print("All three synthetic scenarios finished. No email was sent.")


if __name__ == "__main__":
    main()
