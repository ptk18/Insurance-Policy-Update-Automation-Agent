"""Explicit ``.env`` loading. Values are copied into the process environment only;
they are never logged, returned, or echoed in errors."""

import os
import re
from pathlib import Path

ENV_FILE_VARIABLE = "POLICY_UPDATE_ENV_FILE"
KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def load_env_file(path: Path | None = None) -> list[str]:
    """Load ``KEY=value`` lines from ``path`` (default ``./.env``) into ``os.environ``.

    Variables already set in the shell win, so a deployment can override the file.
    Returns the names that were loaded, never their values."""
    target = path or Path(os.environ.get(ENV_FILE_VARIABLE, ".env"))
    if not target.is_file():
        return []
    loaded = []
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not KEY_PATTERN.fullmatch(key):
            continue
        value = value.strip()
        if value[:1] in {'"', "'"}:
            # Quoted values end at the matching quote; anything after it is ignored.
            closing = value.find(value[0], 1)
            value = value[1:closing] if closing > 0 else value[1:]
        else:
            value = value.split(" #", 1)[0].split("\t#", 1)[0].rstrip()
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
