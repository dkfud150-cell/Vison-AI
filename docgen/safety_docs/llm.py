"""
LLM 연결부 — Claude / OpenAI / mock 중 하나로 JSON을 받아 온다.

- .env 의 LLM_PROVIDER 로 고른다 (mock | claude | openai).
- 모든 호출은 '정해진 JSON 형식(schema)'으로만 받는다. 자유 문장으로 받지 않는다.
- 같은 입력은 cache/ 에 저장해 두고 다시 부르지 않는다.
  → 시연 전에 한 번 실제 API로 돌려 두면, 발표장에서는 네트워크 없이 캐시로 돈다.
- mock 은 API 키 없이 화면·엑셀·워드 흐름을 먼저 확인하는 용도다 (mock/*.json 에 미리 써 둔 답).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from .config import CACHE_DIR, MOCK_DIR, llm_provider


class LLMError(RuntimeError):
    pass


def _image_b64(path: str | Path) -> tuple[str, str]:
    p = Path(path)
    media = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return base64.b64encode(p.read_bytes()).decode("ascii"), media


class LLMClient:
    def __init__(self, provider: str | None = None, use_cache: bool = True):
        self.provider = (provider or llm_provider()).lower()
        self.use_cache = use_cache
        if self.provider not in ("mock", "claude", "openai"):
            raise LLMError(f"LLM_PROVIDER 값이 이상합니다: {self.provider}")

    # ------------------------------------------------------------------ 공통
    def generate_json(self, task: str, system: str, user: str, schema: dict,
                      images: list[str] | None = None, mock_key: str | None = None) -> dict:
        """
        task     : 'assessment' | 'corrective' | 'ptw' | 'accident' — 캐시·mock 파일 이름
        schema   : 받을 JSON 형식 (JSON Schema)
        images   : 함께 보낼 이미지 파일 경로 (시정지시서의 CCTV 프레임)
        mock_key : mock 모드에서 미리 써 둔 답을 찾을 열쇠
        """
        if self.provider == "mock":
            return self._mock(task, mock_key)

        key = self._cache_key(task, system, user, images)
        cache_file = CACHE_DIR / task / f"{key}.json"
        if self.use_cache and cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))

        if self.provider == "claude":
            result = self._claude(system, user, schema, images)
        else:
            result = self._openai(task, system, user, schema, images)

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def _cache_key(self, task, system, user, images) -> str:
        h = hashlib.sha1()
        h.update(f"{self.provider}|{self.model_name()}|{task}|{system}|{user}".encode("utf-8"))
        for p in images or []:
            h.update(Path(p).read_bytes())
        return h.hexdigest()[:16]

    def model_name(self) -> str:
        if self.provider == "claude":
            return os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
        if self.provider == "openai":
            m = os.getenv("OPENAI_MODEL", "").strip()
            if not m:
                raise LLMError(".env 에 OPENAI_MODEL 을 적어 주세요 (쓸 수 있는 비전 지원 모델명).")
            return m
        return "mock"

    # ------------------------------------------------------------------ mock
    def _mock(self, task: str, mock_key: str | None) -> dict:
        path = MOCK_DIR / f"{task}.json"
        table = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if mock_key in table:
            return table[mock_key]
        if "_fallback" in table:
            return table["_fallback"]
        raise LLMError(f"mock 답이 없습니다: {task} / {mock_key}")

    # ------------------------------------------------------------------ Claude
    def _claude(self, system, user, schema, images) -> dict:
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("pip install anthropic 이 필요합니다.") from e
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise LLMError(".env 에 ANTHROPIC_API_KEY 가 없습니다.")

        client = anthropic.Anthropic()
        content = []
        for p in images or []:
            data, media = _image_b64(p)
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": media, "data": data}})
        content.append({"type": "text", "text": user})

        # 도구(tool) 하나를 강제로 부르게 해서, 답을 반드시 schema 모양의 JSON으로 받는다
        resp = client.messages.create(
            model=self.model_name(),
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": content}],
            tools=[{"name": "submit", "description": "결과를 정해진 형식으로 제출한다.",
                    "input_schema": schema}],
            tool_choice={"type": "tool", "name": "submit"},
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise LLMError("Claude 응답에 결과가 없습니다.")

    # ------------------------------------------------------------------ OpenAI
    def _openai(self, task, system, user, schema, images) -> dict:
        try:
            import openai
        except ImportError as e:
            raise LLMError("pip install openai 가 필요합니다.") from e
        if not os.getenv("OPENAI_API_KEY"):
            raise LLMError(".env 에 OPENAI_API_KEY 가 없습니다.")

        client = openai.OpenAI()
        content = [{"type": "text", "text": user}]
        for p in images or []:
            data, media = _image_b64(p)
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{media};base64,{data}"}})

        resp = client.chat.completions.create(
            model=self.model_name(),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": content}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": task, "schema": schema}},
        )
        text = resp.choices[0].message.content or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"OpenAI 응답이 JSON이 아닙니다: {text[:200]}") from e
