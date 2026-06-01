#!/usr/bin/env python3
"""Debug preflight: log which Python/uvicorn would run and whether asyncpg is importable."""
import json
import shutil
import sys
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / ".cursor" / "debug-e591c6.log"
SESSION = "e591c6"


def log(hypothesis_id: str, message: str, data: dict) -> None:
    entry = {
        "sessionId": SESSION,
        "timestamp": int(time.time() * 1000),
        "hypothesisId": hypothesis_id,
        "location": "scripts/debug_env_check.py",
        "message": message,
        "data": data,
        "runId": "preflight",
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    venv_dir = root / ".venv"
    venv_python = venv_dir / "bin" / "python"
    venv_uvicorn = venv_dir / "bin" / "uvicorn"
    activate = venv_dir / "bin" / "activate"

    venv_uvicorn_shebang = None
    if venv_uvicorn.is_file():
        venv_uvicorn_shebang = venv_uvicorn.read_text(encoding="utf-8").splitlines()[0]

    virtual_env_line = None
    if activate.is_file():
        for line in activate.read_text(encoding="utf-8").splitlines():
            if line.startswith("VIRTUAL_ENV="):
                virtual_env_line = line
                break

    which_uvicorn = shutil.which("uvicorn")
    which_python3 = shutil.which("python3")

    asyncpg_ok = False
    asyncpg_error = None
    try:
        import asyncpg  # noqa: F401

        asyncpg_ok = True
    except Exception as exc:
        asyncpg_error = repr(exc)

    log(
        "A",
        "system python and uvicorn resolution",
        {
            "sys_executable": sys.executable,
            "sys_version": sys.version,
            "which_uvicorn": which_uvicorn,
            "which_python3": which_python3,
        },
    )
    log(
        "B",
        "venv path integrity",
        {
            "venv_dir": str(venv_dir),
            "venv_python_exists": venv_python.is_file(),
            "venv_uvicorn_shebang": venv_uvicorn_shebang,
            "activate_virtual_env_line": virtual_env_line,
            "expected_venv_dir": str(root / ".venv"),
        },
    )
    log(
        "C",
        "asyncpg import on current interpreter",
        {"asyncpg_ok": asyncpg_ok, "asyncpg_error": asyncpg_error},
    )

    venv_asyncpg_ok = None
    if venv_python.is_file():
        import subprocess

        proc = subprocess.run(
            [str(venv_python), "-c", "import asyncpg; print('ok')"],
            capture_output=True,
            text=True,
        )
        venv_asyncpg_ok = proc.returncode == 0
        log(
            "D",
            "asyncpg import via venv python",
            {
                "venv_python": str(venv_python),
                "ok": venv_asyncpg_ok,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            },
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
