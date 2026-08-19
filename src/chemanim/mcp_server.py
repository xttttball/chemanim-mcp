from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from threading import Lock
from typing import Literal, TypedDict

from mcp.server import MCPServer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = PROJECT_ROOT / "build"
MEDIA_DIR = PROJECT_ROOT / "media"
RUN_LOCK = Lock()

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
    log: str


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
    return {
        "status": "rendered" if render else "validated",
        "scene_file": str(scene_file.resolve()),
        "verification_file": str(verification_file.resolve()),
        "video_file": latest_video() if render else None,
        "log": log,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
