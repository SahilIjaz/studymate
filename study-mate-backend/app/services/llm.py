"""Claude client wrapper: streaming answers, query rewriting, question suggestions.

All calls go through the async SDK so a slow completion never blocks the
event loop. SDK exceptions are mapped to typed application errors with
user-readable messages; the raw request id is logged for support.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from app.config import Settings
from app.errors import RateLimitedError, UpstreamError
from app.logging_config import get_logger
from app.services import prompts
from app.services.retrieval import RetrievedChunk

log = get_logger(__name__)

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(slots=True)
class Delta:
    text: str


@dataclass(slots=True)
class Completed:
    model: str
    stop_reason: str | None
    usage: dict[str, Any] = field(default_factory=dict)


StreamEvent = Delta | Completed


class LLMService(Protocol):
    """What the API layer needs from any answer-generating backend."""

    provider: str
    model: str
    fast_model: str

    @property
    def configured(self) -> bool: ...

    def stream_answer(
        self, *, question: str, sources: list[RetrievedChunk], history: list[tuple[str, str]]
    ) -> AsyncIterator[StreamEvent]: ...

    async def condense_question(self, history: list[tuple[str, str]], question: str) -> str: ...

    async def suggest_questions(self, excerpt: str) -> list[str]: ...


class ClaudeService:
    provider = "claude"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.claude_model
        self.fast_model = settings.claude_fast_model
        self._client: anthropic.AsyncAnthropic | None = None
        if settings.anthropic_api_key:
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.claude_timeout_seconds,
                max_retries=2,
            )
        self._use_fallbacks = settings.claude_server_fallbacks

    @property
    def configured(self) -> bool:
        return self._client is not None

    def _require(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            raise UpstreamError(
                "The server has no Claude API key configured.",
                code="llm_not_configured",
                status_code=503,
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
        messages: list[dict[str, Any]] = [{"role": role, "content": content} for role, content in history]
        messages.append({"role": "user", "content": prompts.build_user_turn(question, sources)})

        kwargs: dict[str, Any] = {
            "model": self.settings.claude_model,
            "max_tokens": self.settings.claude_max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": prompts.SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            "messages": messages,
            "output_config": {"effort": self.settings.claude_effort},
        }

        try:
            async for event in self._stream(client, kwargs):
                yield event
        except anthropic.BadRequestError as exc:
            # The fallback beta may not be enabled for every organisation.
            # Degrade once, remember it, and keep serving.
            if self._use_fallbacks and "anthropic-beta" in str(exc):
                log.warning("fallback_beta_unavailable", extra={"detail": str(exc)[:200]})
                self._use_fallbacks = False
                async for event in self._stream(client, kwargs):
                    yield event
            else:
                raise self._map(exc) from exc
        except anthropic.APIError as exc:
            raise self._map(exc) from exc

    async def _stream(
        self, client: anthropic.AsyncAnthropic, kwargs: dict[str, Any]
    ) -> AsyncIterator[StreamEvent]:
        if self._use_fallbacks:
            context = client.beta.messages.stream(**kwargs, betas=[_FALLBACK_BETA], fallbacks="default")
        else:
            context = client.messages.stream(**kwargs)
        async with context as stream:
            async for text in stream.text_stream:
                yield Delta(text)
            final = await stream.get_final_message()
        usage = final.usage.model_dump(exclude_none=True) if final.usage else {}
        log.info(
            "claude_completed",
            extra={
                "model": final.model,
                "stop_reason": final.stop_reason,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "cache_read": usage.get("cache_read_input_tokens"),
                "anthropic_request_id": getattr(final, "_request_id", None),
            },
        )
        if final.stop_reason == "refusal":
            details = getattr(final, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise UpstreamError(
                "Claude declined to answer this request.",
                code="llm_refused",
                status_code=422,
                details={"category": category},
            )
        yield Completed(model=final.model, stop_reason=final.stop_reason, usage=usage)

    # ---------------------------------------------------------------- condense
    async def condense_question(self, history: list[tuple[str, str]], question: str) -> str:
        """Rewrite a follow-up into a standalone retrieval query. Never raises."""
        if not history:
            return question
        try:
            client = self._require()
            response = await client.with_options(timeout=15.0, max_retries=0).messages.create(
                model=self.settings.claude_fast_model,
                max_tokens=300,
                system=prompts.CONDENSE_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": prompts.build_condense_turn(history, question),
                    }
                ],
                output_config={"effort": "low"},
            )
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return text or question
        except Exception as exc:  # noqa: BLE001 - retrieval must never fail because of the rewriter
            log.warning("condense_failed", extra={"detail": str(exc)[:200]})
            return question

    # ----------------------------------------------------------------- suggest
    async def suggest_questions(self, excerpt: str) -> list[str]:
        client = self._require()
        try:
            response = await client.with_options(timeout=30.0).messages.create(
                model=self.settings.claude_fast_model,
                max_tokens=400,
                system=prompts.SUGGEST_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"<excerpt>\n{excerpt[:6000]}\n</excerpt>",
                    }
                ],
                output_config={"effort": "low"},
            )
        except anthropic.APIError as exc:
            raise self._map(exc) from exc
        text = "".join(b.text for b in response.content if b.type == "text")
        return _parse_questions(text)

    # --------------------------------------------------------------- utilities
    def _map(self, exc: anthropic.APIError) -> Exception:
        request_id = getattr(exc, "request_id", None)
        log.warning(
            "claude_error",
            extra={"error": type(exc).__name__, "anthropic_request_id": request_id},
        )
        if isinstance(exc, anthropic.AuthenticationError):
            return UpstreamError("The Claude API key was rejected.", code="llm_auth")
        if isinstance(exc, anthropic.PermissionDeniedError):
            return UpstreamError(
                "This Claude account can't use the configured model.",
                code="llm_forbidden",
            )
        if isinstance(exc, anthropic.NotFoundError):
            return UpstreamError(
                f"Model '{self.settings.claude_model}' isn't available. Check CLAUDE_MODEL.",
                code="llm_model_unavailable",
            )
        if isinstance(exc, anthropic.RateLimitError):
            retry_after = exc.response.headers.get("retry-after", "30")
            return RateLimitedError(
                "Claude is rate-limited right now. Try again in a moment.",
                code="llm_rate_limited",
                headers={"Retry-After": retry_after},
            )
        if isinstance(exc, anthropic.APITimeoutError):
            return UpstreamError("Claude took too long to respond.", code="llm_timeout", status_code=504)
        if isinstance(exc, anthropic.APIConnectionError):
            return UpstreamError(
                "Couldn't reach Claude. Try again shortly.",
                code="llm_unreachable",
                status_code=503,
            )
        if isinstance(exc, anthropic.APIStatusError):
            if exc.status_code >= 500:
                return UpstreamError(
                    "Claude is having trouble. Try again shortly.",
                    code="llm_unavailable",
                )
            return UpstreamError(
                f"Claude rejected the request: {exc.message}",
                code="llm_bad_request",
                status_code=502,
            )
        return UpstreamError("Unexpected error talking to Claude.", code="llm_error")


_LINE_QUESTION = re.compile(r"^\s*(?:[-*\d.)]+\s*)?[\"“]?(.+?\?)[\"”]?\s*$", re.MULTILINE)


def _parse_questions(text: str) -> list[str]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return [str(q).strip() for q in data if str(q).strip()][:4]
        except json.JSONDecodeError:
            pass
    return [m.group(1).strip() for m in _LINE_QUESTION.finditer(text)][:4]


class MockClaudeService:
    """Dev-only stand-in that streams a canned answer built from the sources.

    Enabled with LLM_MOCK=true so the UI can be developed and demoed without
    an API key. Never used when a real key is present.
    """

    configured = True
    provider = "mock"
    model = "mock"
    fast_model = "mock"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def stream_answer(
        self, *, question: str, sources: list[RetrievedChunk], history: list[tuple[str, str]]
    ) -> AsyncIterator[StreamEvent]:
        import asyncio

        lead = f"**Mock answer** for *{question.strip()}* (set `ANTHROPIC_API_KEY` for a real one).\n\n"
        body = []
        for n, item in enumerate(sources[:3], start=1):
            sentence = item.chunk.text.split(". ")[0].strip()
            body.append(f"- {sentence[:220]} [{n}]")
        text = (
            lead
            + "\n".join(body)
            + "\n\n**Key takeaway:** this text came straight from the retrieved passages [1]."
        )
        await asyncio.sleep(0.6)
        for word in text.split(" "):
            yield Delta(word + " ")
            await asyncio.sleep(0.03)
        yield Completed(
            model="mock",
            stop_reason="end_turn",
            usage={"input_tokens": 0, "output_tokens": len(text.split())},
        )

    async def condense_question(self, history: list[tuple[str, str]], question: str) -> str:
        return question

    async def suggest_questions(self, excerpt: str) -> list[str]:
        words = [w.strip(".,;:()") for w in excerpt.split()[:400] if len(w) > 7][:4]
        return [f"What does the document say about {w.lower()}?" for w in words] or [
            "What is this document about?"
        ]
