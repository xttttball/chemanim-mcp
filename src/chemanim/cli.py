from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .chemistry import apply_curated_identity, build_assets
from .deepseek import DeepSeekClient, DeepSeekError, finalize_equation
from .pubchem import verify_scene_with_pubchem


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = PROJECT_ROOT / "build"


def resolve_renderer(requested: str, structure_mode: str) -> str:
    if requested == "auto":
        return "opengl" if structure_mode == "3d" else "cairo"
    return requested


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用 DeepSeek、PubChem、RDKit 和 Manim 生成化学动画"
    )
    parser.add_argument("prompt", help="动画要求，例如：演示乙醇完全燃烧")
    parser.add_argument(
        "--model",
        default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        help="DeepSeek 模型 ID；默认 deepseek-v4-flash",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        help="DeepSeek API 地址",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=int(os.environ.get("DEEPSEEK_TIMEOUT", "90")),
        help="DeepSeek 请求超时秒数；默认 90",
    )
    parser.add_argument(
        "--quality",
        choices=["low", "medium", "high", "4k"],
        default="low",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="只生成 JSON 和 SVG，不调用 Manim",
    )
    parser.add_argument(
        "--structure-mode",
        choices=["2d", "3d"],
        default="2d",
        help="结构式显示模式；默认 2d，3d 使用球棍模型",
    )
    parser.add_argument(
        "--renderer",
        choices=["auto", "cairo", "opengl"],
        default="auto",
        help="渲染器；auto 会让 3d 使用 GPU/OpenGL，2d 使用 Cairo",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        client = DeepSeekClient(base_url=args.base_url, timeout=args.request_timeout)
        print(f"[1/4] 使用 DeepSeek 模型：{args.model}")
        spec = client.generate_scene(args.prompt, args.model)
        corrected = apply_curated_identity(spec.molecules)
        if corrected:
            print("[本地目录] 已预校正常见物质：" + "、".join(corrected))

        print("[2/4] 查询 PubChem，并用 Morgan 指纹比对结构")
        verification = verify_scene_with_pubchem(spec.molecules)
        finalize_equation(spec)

        print("[3/4] RDKit 校验并生成结构资产")
        scene_data = build_assets(spec, BUILD_DIR, structure_mode=args.structure_mode)
        scene_data["verification"] = verification
        scene_file = BUILD_DIR / "scene.json"
        scene_file.write_text(
            json.dumps(scene_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (BUILD_DIR / "verification.json").write_text(
            json.dumps(verification, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"场景描述：{scene_file}")

        if args.no_render:
            return

        quality_flags = {
            "low": "-ql",
            "medium": "-qm",
            "high": "-qh",
            "4k": "-qk",
        }
        renderer = resolve_renderer(args.renderer, args.structure_mode)
        print(f"[4/4] Manim 正在使用 {renderer} 渲染视频")
        render_command = [
            sys.executable,
            "-m",
            "manim",
            quality_flags[args.quality],
            f"--renderer={renderer}",
            "--media_dir",
            str(PROJECT_ROOT / "media"),
        ]
        if renderer == "opengl":
            render_command.extend(["--write_to_movie", "--disable_caching"])
        render_command.extend(
            [str(PROJECT_ROOT / "render_scene.py"), "ChemistryScene"]
        )
        subprocess.run(
            render_command,
            cwd=PROJECT_ROOT,
            check=True,
        )
    except (DeepSeekError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
