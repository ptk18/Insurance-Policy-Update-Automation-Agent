import re
import unicodedata
from typing import Any

from pydantic import EmailStr, TypeAdapter, ValidationError

from policy_update.models import Policy

ALLOWED_FIELDS = frozenset({"mailing_address", "email", "phone"})
email_adapter = TypeAdapter(EmailStr)


def normalize(value: str) -> str:
    # Preserve all letters and numbers; ignore only punctuation, case, and whitespace.
    # Do not guess address abbreviations or use fuzzy identity matching.
    words = re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold())
    return " ".join(words)


def validate_changes(
    changes: dict[str, str], policy: Policy | None, evidence: dict[str, Any] | None
) -> list[dict[str, str]]:
    findings = []

    def issue(code, message):
        findings.append({"code": code, "message": message})

    if not changes or set(changes) - ALLOWED_FIELDS:
        issue("unsupported_fields", "Only mailing address, email, and phone changes are allowed.")
    for key, value in changes.items():
        if not isinstance(value, str) or not value.strip():
            issue("empty_value", f"Provide a nonempty value for {key}.")
    if "email" in changes:
        try:
            email_adapter.validate_python(changes["email"])
        except ValidationError:
            issue("invalid_email", "Provide a valid email address.")
    if "phone" in changes:
        compact = re.sub(r"[\s().-]", "", changes["phone"])
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", compact):
            issue("invalid_phone", "Provide an international phone number with a + country code.")
    if "mailing_address" in changes:
        if evidence is None:
            issue("missing_evidence", "Provide proof of address for the mailing address change.")
        elif not evidence.get("readable") or not evidence.get("certain"):
            issue("uncertain_evidence", "Provide readable, unambiguous proof of address.")
        else:
            if policy and normalize(evidence["name"]) != normalize(policy.holder_name):
                issue("name_conflict", "The evidence name does not match the policyholder.")
            if normalize(evidence["address"]) != normalize(changes["mailing_address"]):
                issue(
                    "address_conflict", "The evidence address does not match the requested address."
                )
    return findings
