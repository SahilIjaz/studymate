"""Gemini provider: the same interface as ClaudeService, backed by Google's GenAI SDK.

Chosen for the free tier. Gemini has no server-side prompt caching for short
prompts and tighter per-minute limits, so 429s are mapped to the same
`llm_rate_limited` error the frontend already understands.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import errors, types

from app.config import Settings
from app.errors import RateLimitedError, UpstreamError
from app.logging_config import get_logger
from app.services import prompts
from app.services.llm import Completed, Delta, StreamEvent, _parse_questions
from app.services.retrieval import RetrievedChunk

log = get_logger(__name__)


class GeminiService:
    provider = "gemini"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.gemini_model
        self.fast_model = settings.gemini_fast_model
        self._client: genai.Client | None = None
        if settings.gemini_api_key:
            self._client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(timeout=int(settings.claude_timeout_seconds * 1000)),
            )

    @property
    def configured(self) -> bool:
        return self._client is not None

    def _require(self) -> genai.Client:
        if self._client is None:
            raise UpstreamError(
                "The server has no Gemini API key configured.", code="llm_not_configured", status_code=503
            )
        return self._client

    # ------------------------------------------------------------------ answer
    async def stream_answer(
        self,
        *,
        question: str,
        sources: list[RetrievedChunk],
        history: list[tuple[str, str]],
    ) -> AsyncIterator[StreamEvent]:
        client = self._require()
        contents = [
            types.Content(
                role="user" if role == "user" else "model", parts=[types.Part.from_text(text=content)]
            )
            for role, content in history
        ]
        contents.append(
            types.Content(
                role="user", parts=[types.Part.from_text(text=prompts.build_user_turn(question, sources))]
            )
        )
        config = types.GenerateContentConfig(
            thinking_config=self._thinking(),
            system_instruction=prompts.SYSTEM_PROMPT,
            max_output_tokens=self.settings.claude_max_tokens,
            temperature=0.3,
        )

        # The free tier returns 503 "high demand" on the newest model fairly
        # often. If that happens before any text has streamed, retry once on
        # the fallback model so the student still gets an answer.
        started = False
        try:
            async for event in self._stream(client, self.model, contents, config):
                started = True
                yield event
        except errors.APIError as exc:
            fallback = self.settings.gemini_fallback_model
            if started or not fallback or fallback == self.model or exc.code not in (429, 503):
                raise self._map(exc) from exc
            log.warning("gemini_fallback", extra={"from": self.model, "to": fallback, "status": exc.code})
            try:
                async for event in self._stream(client, fallback, contents, config):
                    yield event
            except errors.APIError as exc2:
                raise self._map(exc2) from exc2

    async def _stream(
        self,
        client: genai.Client,
        model: str,
        contents: list[types.Content],
        config: types.GenerateContentConfig,
    ) -> AsyncIterator[StreamEvent]:
        usage: dict[str, Any] = {}
        finish: str | None = None
        stream = await client.aio.models.generate_content_stream(
            model=model, contents=contents, config=config
        )
        async for chunk in stream:
            if chunk.text:
                yield Delta(chunk.text)
            if chunk.usage_metadata:
                usage = {
                    "input_tokens": chunk.usage_metadata.prompt_token_count,
                    "output_tokens": chunk.usage_metadata.candidates_token_count,
                }
            if chunk.candidates and chunk.candidates[0].finish_reason:
                finish = str(chunk.candidates[0].finish_reason.name).lower()
        log.info("gemini_completed", extra={"model": model, "finish": finish, **usage})
        if finish in {"safety", "prohibited_content", "blocklist", "spii"}:
            raise UpstreamError(
                "Gemini declined to answer this request.", code="llm_refused", status_code=422
            )
        yield Completed(
            model=model, stop_reason=finish, usage={k: v for k, v in usage.items() if v is not None}
        )

    # ---------------------------------------------------------------- condense
    async def condense_question(self, history: list[tuple[str, str]], question: str) -> str:
        if not history:
            return question
        try:
            client = self._require()
            response = await client.aio.models.generate_content(
                model=self.fast_model,
                contents=prompts.build_condense_turn(history, question),
                config=types.GenerateContentConfig(
                    thinking_config=self._thinking(),
                    system_instruction=prompts.CONDENSE_PROMPT,
                    max_output_tokens=300,
                    temperature=0,
                ),
            )
            return (response.text or "").strip() or question
        except Exception as exc:  # noqa: BLE001 - retrieval must never fail because of the rewriter
            log.warning("condense_failed", extra={"detail": str(exc)[:200]})
            return question

    # ----------------------------------------------------------------- suggest
    async def suggest_questions(self, excerpt: str) -> list[str]:
        client = self._require()
        try:
            response = await client.aio.models.generate_content(
                model=self.fast_model,
                contents=f"<excerpt>\n{excerpt[:6000]}\n</excerpt>",
                config=types.GenerateContentConfig(
                    thinking_config=self._thinking(),
                    system_instruction=prompts.SUGGEST_PROMPT,
                    max_output_tokens=400,
                    response_mime_type="application/json",
                ),
            )
        except errors.APIError as exc:
            raise self._map(exc) from exc
        return _parse_questions(response.text or "")

    # --------------------------------------------------------------- utilities
    def _thinking(self) -> types.ThinkingConfig | None:
        level = self.settings.gemini_thinking_level
        return types.ThinkingConfig(thinking_level=level) if level else None

    def _map(self, exc: errors.APIError) -> Exception:
        log.warning("gemini_error", extra={"status": exc.code, "detail": str(exc.message)[:200]})
        if exc.code == 429:
            return RateLimitedError(
                "Gemini's free-tier limit was hit. Try again in a moment.",
                code="llm_rate_limited",
                headers={"Retry-After": "30"},
            )
        if exc.code in (401, 403):
            return UpstreamError("The Gemini API key was rejected.", code="llm_auth")
        if exc.code == 404:
            return UpstreamError(
                f"Model '{self.model}' isn't available. Check GEMINI_MODEL.", code="llm_model_unavailable"
            )
        if exc.code == 503:
            return UpstreamError(
                "Gemini is overloaded right now. Try again in a moment.",
                code="llm_unavailable",
                status_code=503,
            )
        if exc.code and exc.code >= 500:
            return UpstreamError("Gemini is having trouble. Try again shortly.", code="llm_unavailable")
        return UpstreamError(
            f"Gemini rejected the request: {exc.message}", code="llm_bad_request", status_code=502
        )
