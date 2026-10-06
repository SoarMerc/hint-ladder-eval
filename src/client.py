"""Gemini calls, plus retries, caching and cost tracking.

Everything goes through json_call, which asks for a schema-constrained JSON
response. Nothing here parses free text.

--mock replaces the network at this layer only, so generation, grading,
detection and reporting all run unchanged. Mock runs are reproducible from the
seed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .config import CACHE, ROOT, Config
from .schemas import CostLine

logger = logging.getLogger("hintladder")


# --------------------------------------------------------------------------
# Response contracts. Gemini takes a Pydantic class directly as its response
# schema, so these double as the wire schema and the validation step.
# --------------------------------------------------------------------------


class AuthorOut(BaseModel):
    question: str
    answer: str
    hints: list[str]


class TranslateOut(BaseModel):
    question: str
    hints: list[str]


class StudentOut(BaseModel):
    answer: str


class JudgeOut(BaseModel):
    equivalent: bool


class TagOut(BaseModel):
    code: str


_SCHEMAS: dict[str, type[BaseModel]] = {
    "author": AuthorOut,
    "translate": TranslateOut,
    "student": StudentOut,
    "judge": JudgeOut,
    "tag": TagOut,
}


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader so the harness has no extra runtime dependency."""
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


class ModelClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._sem = asyncio.Semaphore(cfg.concurrency)
        self._costs: dict[str, CostLine] = {}
        self._client = None
        self._types = None

        if not cfg.mock:
            load_dotenv()
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is empty. Put your key in .env (it is "
                    "gitignored), or run with --mock."
                )
            from google import genai
            from google.genai import types

            self._client = genai.Client(api_key=api_key)
            self._types = types

        CACHE.mkdir(parents=True, exist_ok=True)

    # -- public ------------------------------------------------------------

    async def json_call(
        self,
        *,
        kind: str,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 2048,
        think: bool = True,
        temperature: float = 0.2,
        cache_salt: str = "",
        ctx: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make one schema-constrained call, or serve it from cache.

        `cache_salt` distinguishes repeated identical prompts, which is what
        the student sweep does: five attempts at the same cell must not
        collapse into one cache entry, or the measurement loses its variance.
        """
        key = self._cache_key(kind, model, system, user + "\x00" + cache_salt)
        if self.cfg.use_cache:
            cached = self._read_cache(key)
            if cached is not None:
                return cached

        async with self._sem:
            if self.cfg.mock:
                data = _mock_call(kind, ctx or {}, self.cfg.seed)
            else:
                data = await self._call_with_retry(
                    kind=kind,
                    model=model,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    think=think,
                    temperature=temperature,
                )

        if self.cfg.use_cache:
            self._write_cache(key, data)
        return data

    def costs(self) -> list[CostLine]:
        return sorted(self._costs.values(), key=lambda c: -c.usd)

    # -- live path ---------------------------------------------------------

    async def _call_with_retry(self, **kwargs: Any) -> dict[str, Any]:
        """Linear backoff over transient failures (503s, timeouts, throttling)."""
        last: Exception | None = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                return await self._live_call(**kwargs)
            except Exception as exc:  # noqa: BLE001 - we want to retry anything
                last = exc
                if attempt == self.cfg.max_retries:
                    break
                wait = self.cfg.retry_delay * attempt
                logger.warning(
                    "Gemini call failed (%s). Retrying in %ss " "(attempt %s/%s): %s",
                    kwargs.get("kind"),
                    wait,
                    attempt,
                    self.cfg.max_retries,
                    exc,
                )
                await asyncio.sleep(wait)
        raise RuntimeError(
            f"Gemini call '{kwargs.get('kind')}' failed after "
            f"{self.cfg.max_retries} attempts"
        ) from last

    async def _live_call(
        self,
        *,
        kind: str,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        think: bool,
        temperature: float,
    ) -> dict[str, Any]:
        types = self._types
        schema = _SCHEMAS[kind]

        cfg_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "response_mime_type": "application/json",
            "response_schema": schema,
        }
        if not think:
            # Off for the student - we don't want it reasoning its way there.
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

        resp = await self._client.aio.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        self._record(model, resp)

        parsed = getattr(resp, "parsed", None)
        if isinstance(parsed, BaseModel):
            return parsed.model_dump()

        text = (resp.text or "").strip()
        if not text:
            raise RuntimeError(f"{model} returned an empty body for '{kind}'")
        return schema.model_validate_json(text).model_dump()

    def _record(self, model: str, resp: Any) -> None:
        usage = getattr(resp, "usage_metadata", None)
        if usage is None:
            return
        in_tok = int(getattr(usage, "prompt_token_count", 0) or 0)
        out_tok = int(getattr(usage, "candidates_token_count", 0) or 0)
        # Thinking tokens bill as output.
        out_tok += int(getattr(usage, "thoughts_token_count", 0) or 0)

        from .config import PRICES

        line = self._costs.setdefault(
            model, CostLine(model=model, priced=model in PRICES)
        )
        p_in, p_out = self.cfg.price(model)
        line.calls += 1
        line.input_tokens += in_tok
        line.output_tokens += out_tok
        line.usd += (in_tok * p_in + out_tok * p_out) / 1_000_000

    # -- cache -------------------------------------------------------------

    def _cache_key(self, kind: str, model: str, system: str, user: str) -> str:
        """Mode is part of the key.

        Without it a mock run poisons the cache and a later real run replays
        fake answers while reporting no spend. That happened; hence the test.
        """
        mode = "mock" if self.cfg.mock else "live"
        blob = "\x00".join([mode, kind, model, system, user]).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:32]

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        path = CACHE / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, key: str, data: dict[str, Any]) -> None:
        (CACHE / f"{key}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )


# --------------------------------------------------------------------------
# Mock simulator
#
# Lets the pipeline run without a key, and gives the detector ladders whose
# true leak level is known so it can be scored. Mock numbers are simulated, not
# measured, and FINDINGS.md says so at the top.
# --------------------------------------------------------------------------

_LEAK_MARKER = "the answer is"


def _rng(*parts: Any) -> random.Random:
    return random.Random(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest())


def _planted_leak_level(skill: str, language: str, seed: int, max_level: int) -> int:
    """Where the simulated ladder actually gives the answer away."""
    r = _rng("leak", skill, seed)
    base = max_level if r.random() > 0.30 else r.choice([2, 3])
    if language != "en":
        # Simulates the effect this add-on looks for: scaffolding tuned in one
        # language degrading under translation.
        r2 = _rng("degrade", skill, language, seed)
        if r2.random() < 0.45:
            base = max(2, base - 1)
    return base


def _planted_answer(skill: str, seed: int) -> str:
    r = _rng("answer", skill, seed)
    return f"{skill.replace('.', '')}-{r.randint(100, 999)}"


def _mock_call(kind: str, ctx: dict[str, Any], seed: int) -> dict[str, Any]:
    skill = ctx.get("skill", "?")
    language = ctx.get("language", "en")
    max_level = int(ctx.get("max_level", 4))

    if kind in {"author", "translate"}:
        answer = _planted_answer(skill, seed)
        leak = _planted_leak_level(skill, language, seed, max_level)
        hints = []
        for level in range(1, max_level + 1):
            if level >= leak:
                hints.append(
                    f"[{language}] hint {level} for {skill}: work it through and "
                    f"note that {_LEAK_MARKER} {answer}."
                )
            else:
                hints.append(
                    f"[{language}] hint {level} for {skill}: a level-{level} nudge "
                    f"that narrows the approach without stating the result."
                )
        out: dict[str, Any] = {
            "question": f"[{language}] simulated {skill} question",
            "hints": hints,
        }
        if kind == "author":
            out["answer"] = answer
        return out

    if kind == "student":
        shown: list[str] = ctx.get("hints_shown", [])
        answer = _planted_answer(skill, seed)
        leaking = any(_LEAK_MARKER in h for h in shown)

        if ctx.get("condition", "hints_only") == "hints_only":
            # Without the question there is nothing to reason from, so the only
            # way to produce the answer is for a hint to have carried it.
            return {"answer": answer if leaking else "UNKNOWN"}

        if leaking:
            return {"answer": answer}
        # With the question in hand, partial credit rises gently with the number
        # of non-leaking hints, which is what a good ladder looks like.
        r = _rng("attempt", skill, language, len(shown), ctx.get("repeat", 0), seed)
        p = min(0.12 + 0.14 * len(shown), 0.75)
        return {"answer": answer if r.random() < p else "not sure"}

    if kind == "judge":
        a = str(ctx.get("truth", "")).strip().lower()
        b = str(ctx.get("response", "")).strip().lower()
        return {"equivalent": a == b}

    if kind == "tag":
        r = _rng("tag", skill, seed)
        if r.random() < 0.85:
            return {"code": skill}
        return {"code": ctx.get("distractor", skill)}

    raise ValueError(f"unknown mock call kind: {kind}")


def normalize(text: str) -> str:
    """Loose normalisation used by the exact-match fast path in grading."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s./-]", "", text)
    return re.sub(r"\s+", " ", text).strip()
