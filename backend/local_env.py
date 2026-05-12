from __future__ import annotations

import os
import re
from pathlib import Path


ALLOWED_LOCAL_ENV_KEYS = {
    "OPENAI_API_KEY",
    "REVIEW_CAPTURE",
    "SCOPELEDGER_ALLOWED_IMPORT_ROOTS",
    "SCOPELEDGER_CLOUDHAMMER_MODEL",
    "SCOPELEDGER_CLOUDHAMMER_TIMEOUT_SECONDS",
    "SCOPELEDGER_MAX_UPLOAD_BYTES",
    "SCOPELEDGER_PREREVIEW_BATCH_SIZE",
    "SCOPELEDGER_PREREVIEW_ENABLED",
    "SCOPELEDGER_PREREVIEW_MODEL",
    "SCOPELEDGER_WEBAPP_SECRET",
}
LOCAL_ENV_CANDIDATES = (".env", "CloudHammer/.env")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_local_env_defaults(project_root: Path | None = None) -> tuple[Path, ...]:
    """Load allowlisted local env defaults without overriding process env."""

    root = (project_root or Path.cwd()).resolve()
    loaded_paths: list[Path] = []
    for relative_path in LOCAL_ENV_CANDIDATES:
        env_path = (root / relative_path).resolve()
        if not env_path.is_file():
            continue
        loaded_any = False
        for key, value in parse_env_file(env_path).items():
            if key not in ALLOWED_LOCAL_ENV_KEYS or value == "":
                continue
            if os.environ.get(key, ""):
                continue
            os.environ[key] = value
            loaded_any = True
        if loaded_any:
            loaded_paths.append(env_path)
    return tuple(loaded_paths)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        values[key] = value
    return values


def parse_env_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].lstrip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    if not ENV_KEY_RE.fullmatch(key):
        return None
    return key, _clean_env_value(value.strip())


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        quote = value[0]
        value = value[1:-1]
        if quote == '"':
            return value.replace(r"\"", '"').replace(r"\\", "\\")
        return value
    for marker in (" #", "\t#"):
        if marker in value:
            value = value.split(marker, 1)[0].rstrip()
    return value
