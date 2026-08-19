from __future__ import annotations

import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from .chemistry import balance_equation_from_molecules, validate_molecules
from .spec import SceneSpec, validate_formula_references


SYSTEM_PROMPT = """You are a rigorous chemistry animation planner.
Reason with English IUPAC or conventional chemical names,
but keep title and name fields in Chinese.
Return JSON only, matching this exact shape:
{
  "title": "中文标题",
  "equation": "balanced mhchem body such as CH4 + 2 O2 -> CO2 + 2 H2O",
  "molecules": [{
    "name": "中文显示名",
    "canonical_name": "English IUPAC or conventional name suitable for PubChem lookup",
    "formula": "molecular formula without charge or state",
    "charge": 0,
    "smiles": "isomeric SMILES including @/@@ stereochemistry when relevant",
    "role": "reactant|product|catalyst|other",
    "show_hydrogens": false
  }]
}
Rules:
1. Include every displayed reactant and product, at most six molecules.
2. Use a balanced equation without LaTeX commands.
3. Preserve stereochemistry in isomeric SMILES.
4. canonical_name must be an unambiguous English database lookup term.
5. Do not invent unsupported reaction conditions or execute code.
"""


class DeepSeekError(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com",
        timeout: int = 90,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise DeepSeekError(
                "缺少 DEEPSEEK_API_KEY。请先在 PowerShell 设置环境变量。"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, payload: dict) -> dict:
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        print(f"[DeepSeek] 请求已发送，等待响应（超时 {self.timeout} 秒）...", flush=True)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                print("[DeepSeek] 已收到响应", flush=True)
                return result
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise DeepSeekError(f"DeepSeek HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise DeepSeekError(f"无法连接 DeepSeek API：{exc.reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise DeepSeekError(
                f"DeepSeek 在 {self.timeout} 秒内没有响应。"
                "请重试，或用 --request-timeout 调大超时。"
            ) from exc

    def generate_scene(self, prompt: str, model: str) -> SceneSpec:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt + "\nReturn the result as JSON."},
        ]
        last_error: Exception | None = None

        for attempt in range(3):
            result = self._request(
                {
                    "model": model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "thinking": {"type": "disabled"},
                    "temperature": 0.1,
                    "max_tokens": 2000,
                    "stream": False,
                }
            )
            raw = ""
            try:
                raw = result["choices"][0]["message"]["content"]
                if not raw.strip():
                    raise ValueError("DeepSeek returned empty JSON content")
                return SceneSpec.model_validate_json(raw)
            except (KeyError, TypeError, ValidationError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    print(
                        f"[规划] 第 {attempt + 1} 次 JSON/SMILES 无效，"
                        f"正在返回 DeepSeek 修正：{exc}"
                    )
                    messages.extend(
                        [
                            {"role": "assistant", "content": raw},
                            {
                                "role": "user",
                                "content": (
                                    f"Validation failed: {exc}. Correct the complete JSON. "
                                    "Check English names, formulae, stereochemistry, and SMILES."
                                ),
                            },
                        ]
                    )

        raise DeepSeekError(f"DeepSeek 连续三次生成无效场景：{last_error}")


def finalize_equation(spec: SceneSpec) -> None:
    """Validate verified structures and deterministically balance the equation."""
    validate_molecules(spec.molecules)
    equation = balance_equation_from_molecules(spec.molecules)
    if equation is not None and equation != spec.equation:
        spec.equation = equation
        print("[校验] 已按 PubChem 结构、原子和电荷守恒重建方程式：" + equation)
    validate_formula_references(spec)
