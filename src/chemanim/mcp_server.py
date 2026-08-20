from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock
from typing import Literal, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from mcp.server import MCPServer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = PROJECT_ROOT / "build"
MEDIA_DIR = PROJECT_ROOT / "media"
RUN_LOCK = Lock()
BUILD_ID = "xttttball-upload-v1"

mcp = MCPServer(
    "ChemAnim",
    instructions=(
        "Generate chemistry animations through DeepSeek planning, PubChem lookup, "
        "Morgan fingerprint comparison, RDKit validation, and Manim rendering."
    ),
)


class GenerationResult(TypedDict):
    status: str
    scene_file: str
    verification_file: str
    video_file: str | None
    video_url: str | None
    log: str


class RuntimeDiagnostic(TypedDict):
    build_id: str
    upload_url_configured: bool
    upload_token_configured: bool
    health_url: str | None
    upload_server_status: int | None
    upload_server_ok: bool
    upload_server_error: str | None


def build_command(
    prompt: str,
    quality: str,
    structure_mode: str,
    render: bool,
    model: str,
    request_timeout: int,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "chemanim.cli",
        prompt,
        "--quality",
        quality,
        "--structure-mode",
        structure_mode,
        "--request-timeout",
        str(request_timeout),
    ]
    if not render:
        command.append("--no-render")
    if model:
        command.extend(["--model", model])
    return command


def latest_video() -> str | None:
    if not MEDIA_DIR.exists():
        return None
    videos = [
        path
        for path in MEDIA_DIR.rglob("*.mp4")
        if "partial_movie_files" not in path.parts
    ]
    return str(max(videos, key=lambda path: path.stat().st_mtime).resolve()) if videos else None


def upload_video(video_file: str) -> str | None:
    """Upload a rendered MP4 and return its public URL.

    Uploading is optional. If CHEMANIM_UPLOAD_URL is not configured, the
    original local-only behaviour is preserved and ``None`` is returned.
    """
    upload_url = os.environ.get("CHEMANIM_UPLOAD_URL", "").strip()
    upload_token = os.environ.get("CHEMANIM_UPLOAD_TOKEN", "").strip()

    if not upload_url:
        return None
    if not upload_token:
        raise RuntimeError(
            "CHEMANIM_UPLOAD_URL is configured but CHEMANIM_UPLOAD_TOKEN is missing"
        )

    video_path = Path(video_file)
    if not video_path.is_file():
        raise RuntimeError(f"Rendered video does not exist: {video_path}")

    boundary = f"----ChemAnimBoundary{uuid4().hex}"
    filename = video_path.name
    file_data = video_path.read_bytes()

    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        ).encode("utf-8")
    )
    body.extend(b"Content-Type: video/mp4\r\n\r\n")
    body.extend(file_data)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    request = Request(
        upload_url,
        data=bytes(body),
        method="POST",
        headers={
            "Authorization": f"Bearer {upload_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=120) as response:
            raw_response = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Video upload failed with HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Video upload failed: {exc.reason}") from exc

    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Upload server returned invalid JSON: {raw_response[:500]}"
        ) from exc

    video_url = payload.get("video_url")
    if not isinstance(video_url, str) or not video_url.strip():
        raise RuntimeError(f"Upload server did not return video_url: {payload}")

    return video_url.strip()


@mcp.tool()
def diagnose_runtime() -> RuntimeDiagnostic:
    """Report runtime build identity, upload env presence, and upload server reachability."""
    upload_url = os.environ.get("CHEMANIM_UPLOAD_URL", "").strip()
    upload_token = os.environ.get("CHEMANIM_UPLOAD_TOKEN", "").strip()

    if not upload_url:
        return {
            "build_id": BUILD_ID,
            "upload_url_configured": False,
            "upload_token_configured": bool(upload_token),
            "health_url": None,
            "upload_server_status": None,
            "upload_server_ok": False,
            "upload_server_error": "CHEMANIM_UPLOAD_URL is not configured",
        }

    health_url = upload_url.rsplit("/", 1)[0] + "/health"
    request = Request(
        health_url,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": "ChemAnim-Diagnostics/1.0"},
    )

    status: int | None = None
    error: str | None = None
    ok = False

    try:
        with urlopen(request, timeout=10) as response:
            status = response.status
            ok = 200 <= status < 300
    except HTTPError as exc:
        status = exc.code
        error = f"HTTP {exc.code}"
    except URLError as exc:
        error = str(exc.reason)
    except Exception as exc:  # defensive: diagnostics should report, not crash
        error = str(exc)

    return {
        "build_id": BUILD_ID,
        "upload_url_configured": True,
        "upload_token_configured": bool(upload_token),
        "health_url": health_url,
        "upload_server_status": status,
        "upload_server_ok": ok,
        "upload_server_error": error,
    }


@mcp.tool()
def generate_chemistry_animation(
    prompt: str,
    quality: Literal["low", "medium", "high", "4k"] = "medium",
    structure_mode: Literal["2d", "3d"] = "2d",
    render: bool = True,
    model: str = "",
    request_timeout: int = 90,
) -> GenerationResult:
    """Generate and validate a chemistry scene, optionally rendering an MP4."""
    if not prompt.strip():
        raise ValueError("prompt cannot be empty")
    if not 10 <= request_timeout <= 600:
        raise ValueError("request_timeout must be between 10 and 600 seconds")

    command = build_command(
        prompt, quality, structure_mode, render, model, request_timeout
    )
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    # ponytail: one shared output directory; add per-job directories if concurrency is needed.
    with RUN_LOCK:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=request_timeout + (7200 if render else 120),
            creationflags=creationflags,
            check=False,
        )

    log = (result.stdout + result.stderr)[-4000:]
    if result.returncode != 0:
        raise RuntimeError(log or f"chemanim exited with code {result.returncode}")

    scene_file = BUILD_DIR / "scene.json"
    verification_file = BUILD_DIR / "verification.json"
    video_file = latest_video() if render else None
    video_url = upload_video(video_file) if video_file else None

    return {
        "status": "rendered" if render else "validated",
        "scene_file": str(scene_file.resolve()),
        "verification_file": str(verification_file.resolve()),
        "video_file": video_file,
        "video_url": video_url,
        "log": log,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
