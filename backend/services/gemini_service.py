"""
Gemini Service
==============
The **single, authoritative** gateway to Google's Gemini API for the entire
PulseOS backend.

SDK: google-genai (official Google Gen AI Python SDK)
     https://googleapis.github.io/python-genai/

Design contract
---------------
* No other module may import ``google.genai`` directly.
* Every AI feature (Copilot, Recommendation Engine, Executive Summary, XAI)
  MUST route its LLM calls through ``GeminiService``.
* ``GeminiService`` is stateless and safe to inject per-request via FastAPI
  ``Depends()``.  Use ``@lru_cache`` on the provider in ``deps.py`` if you
  want a shared singleton (client creation is cheap, but model loading is not).

Public API
----------
``generate(prompt, **overrides)``
    Single-shot text generation.

``generate_with_context(prompt, context, **overrides)``
    Single-shot generation with a prepended context block.

``generate_json(prompt, max_retries, **overrides)``
    Generation with automatic JSON extraction + retry on malformed output.

``stream(prompt, **overrides)``
    Yields text chunks as they arrive from the Gemini streaming API.

Prompt helpers (do NOT call the API)
-------------------------------------
``build_summary_prompt(data)``
``build_recommendation_prompt(metrics, predictions)``
``build_explanation_prompt(action, context)``
``build_chat_prompt(history, user_message)``

Error handling
--------------
All public methods catch Gemini / network exceptions and raise a structured
``GeminiServiceError`` (or one of its typed sub-classes) instead of
propagating raw SDK exceptions.  The backend never crashes because of an LLM
call.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, Iterator, List, Optional

import config

# ---------------------------------------------------------------------------
# Lazy SDK import — keeps the module importable even when the package is not
# installed (e.g. during CI / unit tests that do not hit Gemini).
# ---------------------------------------------------------------------------
try:
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types

    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]
    genai_errors = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]
    _SDK_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typed exception hierarchy
# (unchanged — preserves the contract for all callers)
# ---------------------------------------------------------------------------


class GeminiServiceError(Exception):
    """Base class for all errors raised by GeminiService."""

    def __init__(self, message: str, *, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.cause = cause

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable representation suitable for JSON API responses."""
        return {
            "error": type(self).__name__,
            "message": str(self),
            "cause": str(self.cause) if self.cause else None,
        }


class GeminiAuthError(GeminiServiceError):
    """Raised when the API key is missing or rejected (HTTP 401)."""


class GeminiQuotaError(GeminiServiceError):
    """Raised when the API quota is exceeded (HTTP 429)."""


class GeminiTimeoutError(GeminiServiceError):
    """Raised when the API call times out or the service is unavailable (HTTP 503/504)."""


class GeminiEmptyResponseError(GeminiServiceError):
    """Raised when the model returns an empty or safety-blocked response."""


class GeminiMalformedJSONError(GeminiServiceError):
    """Raised when all retries for JSON generation are exhausted."""


class GeminiSDKUnavailableError(GeminiServiceError):
    """Raised when the ``google-genai`` package is not installed."""


# ---------------------------------------------------------------------------
# Generation configuration class
# ---------------------------------------------------------------------------


class GenerationConfig:
    """
    Tuneable knobs forwarded to ``types.GenerateContentConfig`` on every call.

    All fields default to ``None`` so that only explicitly set values override
    the model defaults.  ``system_instruction`` is passed here (not at client
    construction time, which is the new SDK pattern).
    """

    def __init__(
        self,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        system_instruction: Optional[str] = None,
    ) -> None:
        self.temperature = temperature
        self.top_p = top_p
        self.max_output_tokens = max_output_tokens
        self.system_instruction = system_instruction

    def to_sdk_config_dict(self) -> Dict[str, Any]:
        """
        Returns a dict with only the non-None fields.

        Used to construct ``types.GenerateContentConfig`` via ``**`` unpacking.
        """
        cfg: Dict[str, Any] = {}
        if self.temperature is not None:
            cfg["temperature"] = self.temperature
        if self.top_p is not None:
            cfg["top_p"] = self.top_p
        if self.max_output_tokens is not None:
            cfg["max_output_tokens"] = self.max_output_tokens
        if self.system_instruction is not None:
            cfg["system_instruction"] = self.system_instruction
        return cfg


# ---------------------------------------------------------------------------
# Default configuration — sourced from config.py / env vars
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = GenerationConfig(
    temperature=float(getattr(config, "GEMINI_TEMPERATURE", 0.7)),
    top_p=float(getattr(config, "GEMINI_TOP_P", 0.95)),
    max_output_tokens=int(getattr(config, "GEMINI_MAX_TOKENS", 8192)),
    system_instruction=getattr(
        config,
        "GEMINI_SYSTEM_INSTRUCTION",
        (
            "You are PulseOS, an advanced AI assistant for autonomous telecom "
            "network operations. Provide concise, accurate, and actionable "
            "responses. When asked for JSON, return ONLY valid JSON — no "
            "markdown fences, no prose."
        ),
    ),
)

_JSON_RETRY_ATTEMPTS: int = int(getattr(config, "GEMINI_JSON_RETRY_ATTEMPTS", 3))
_JSON_RETRY_DELAY_S: float = float(getattr(config, "GEMINI_JSON_RETRY_DELAY_S", 1.0))


# ---------------------------------------------------------------------------
# HTTP status-code constants for exception mapping
# ---------------------------------------------------------------------------
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_INTERNAL_SERVER_ERROR = 500
_HTTP_SERVICE_UNAVAILABLE = 503
_HTTP_GATEWAY_TIMEOUT = 504


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class GeminiService:
    """
    Sole gateway to the Google Gemini generative API.

    Uses the official ``google-genai`` SDK (``from google import genai``).
    The client is created lazily on first use, so import-time cost is zero.

    Parameters
    ----------
    api_key:
        Gemini API key.  Defaults to ``config.GEMINI_API_KEY``.
    model_name:
        Gemini model identifier.  Defaults to ``config.GEMINI_MODEL``.
    default_config:
        ``GenerationConfig`` applied to every call unless overridden.
    """

    # ------------------------------------------------------------------
    # Construction / initialisation
    # ------------------------------------------------------------------

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        default_config: Optional[GenerationConfig] = None,
    ) -> None:
        if not _SDK_AVAILABLE:
            raise GeminiSDKUnavailableError(
                "The 'google-genai' package is not installed.  "
                "Run: pip install google-genai"
            )

        self._api_key: str = api_key or config.GEMINI_API_KEY
        self._model_name: str = model_name or config.GEMINI_MODEL
        self._default_cfg: GenerationConfig = default_config or _DEFAULT_CONFIG

        # The genai.Client is lightweight; it does NOT open a connection at
        # construction time.  Kept as an instance attribute so that the
        # @lru_cache singleton in deps.py reuses the same underlying HTTP
        # session across requests.
        self._client: Optional[Any] = None  # lazy — created on first call

        self._validate_api_key()
        logger.info(
            "GeminiService initialised | model=%s | temp=%s",
            self._model_name,
            self._default_cfg.temperature,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_api_key(self) -> None:
        """Raises ``GeminiAuthError`` immediately if the key is absent."""
        if not self._api_key or not self._api_key.strip():
            raise GeminiAuthError(
                "GEMINI_API_KEY is not set.  "
                "Export the environment variable before starting PulseOS."
            )

    def _get_client(self) -> Any:
        """
        Returns the cached ``genai.Client`` instance, creating it lazily.

        In the new SDK, ``genai.Client(api_key=...)`` replaces the old
        ``genai.configure(api_key=...)`` + ``genai.GenerativeModel(...)``
        pattern.  The client is thread-safe and connection-pooled.
        """
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
            logger.debug(
                "genai.Client created | model target=%s", self._model_name
            )
        return self._client

    def _build_sdk_config(self, overrides: Dict[str, Any]) -> Any:
        """
        Merges ``_default_cfg`` with caller-supplied overrides and returns a
        ``types.GenerateContentConfig`` instance.

        In the new SDK, ``system_instruction`` is part of
        ``GenerateContentConfig`` (not a model constructor argument).
        Supported override keys: ``temperature``, ``top_p``,
        ``max_output_tokens``, ``system_instruction``.
        """
        merged = self._default_cfg.to_sdk_config_dict()
        # Only apply overrides that are explicitly non-None
        merged.update({k: v for k, v in overrides.items() if v is not None})
        return genai_types.GenerateContentConfig(**merged)

    @staticmethod
    def _extract_text(response: Any) -> str:
        """
        Safely extracts the text from a ``GenerateContentResponse``.

        The new SDK still exposes ``response.text`` as a convenience property.
        Raises ``GeminiEmptyResponseError`` if the response is blocked or empty.
        """
        try:
            text = response.text
        except (AttributeError, ValueError) as exc:
            raise GeminiEmptyResponseError(
                "Gemini returned an empty or safety-blocked response.",
                cause=exc,
            ) from exc

        if not text or not text.strip():
            raise GeminiEmptyResponseError(
                "Gemini returned a blank response body."
            )
        return text.strip()

    @staticmethod
    def _parse_json(text: str) -> Any:
        """
        Attempts to parse JSON from the model's text output.

        Handles the common case where the model wraps JSON in markdown fences
        (e.g. ```json ... ```) even when instructed not to.
        """
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
        payload = fence_match.group(1).strip() if fence_match else text.strip()
        return json.loads(payload)

    def _map_sdk_exception(self, exc: Exception) -> GeminiServiceError:
        """
        Converts a raw ``google.genai.errors.APIError`` (or any other
        exception) into a typed ``GeminiServiceError`` sub-class.

        The new SDK uses ``genai_errors.APIError`` with an integer
        ``status_code`` attribute that maps to standard HTTP codes:
          401 / 403 → GeminiAuthError
          429       → GeminiQuotaError
          503 / 504 → GeminiTimeoutError
        """
        if genai_errors is not None and isinstance(exc, genai_errors.APIError):
            status: Optional[int] = getattr(exc, "status_code", None)
            exc_str = str(exc).lower()

            if status in (_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN):
                return GeminiAuthError(
                    "Invalid or expired API key.", cause=exc
                )
            if status == _HTTP_TOO_MANY_REQUESTS or "quota" in exc_str or "rate limit" in exc_str:
                return GeminiQuotaError(
                    "Gemini API quota or rate limit exceeded.", cause=exc
                )
            if status in (_HTTP_SERVICE_UNAVAILABLE, _HTTP_GATEWAY_TIMEOUT):
                return GeminiTimeoutError(
                    "Gemini API timed out or service is unavailable.", cause=exc
                )
            if status == _HTTP_INTERNAL_SERVER_ERROR:
                return GeminiServiceError(
                    f"Gemini API internal server error (500): {exc}", cause=exc
                )
            return GeminiServiceError(
                f"Gemini API error (HTTP {status}): {exc}", cause=exc
            )

        # Fallback for non-APIError exceptions (e.g. network errors)
        exc_str = str(exc).lower()
        if "timeout" in exc_str or "timed out" in exc_str or "deadline" in exc_str:
            return GeminiTimeoutError(str(exc), cause=exc)
        if "quota" in exc_str or "rate limit" in exc_str:
            return GeminiQuotaError(str(exc), cause=exc)
        if "api key" in exc_str or "invalid key" in exc_str or "unauthenticated" in exc_str:
            return GeminiAuthError(str(exc), cause=exc)

        return GeminiServiceError(f"Gemini SDK error: {exc}", cause=exc)

    # ------------------------------------------------------------------
    # Core generation methods  (public API — unchanged signatures)
    # ------------------------------------------------------------------

    def generate(self, prompt: str, **overrides: Any) -> str:
        """
        Single-shot text generation.

        Parameters
        ----------
        prompt:
            The complete prompt to send to the model.
        **overrides:
            Optional ``GenerationConfig`` field overrides:
            ``temperature``, ``top_p``, ``max_output_tokens``,
            ``system_instruction``.

        Returns
        -------
        str
            The model's text response (stripped of leading/trailing whitespace).

        Raises
        ------
        GeminiAuthError
            If the API key is invalid (HTTP 401/403).
        GeminiQuotaError
            If the quota or rate limit is exceeded (HTTP 429).
        GeminiTimeoutError
            If the request times out or the service is unavailable (HTTP 503/504).
        GeminiEmptyResponseError
            If the model returns a blank or safety-blocked response.
        GeminiServiceError
            For any other unexpected SDK error.
        """
        logger.debug("generate() | prompt_len=%d", len(prompt))
        try:
            client = self._get_client()
            sdk_config = self._build_sdk_config(overrides)
            response = client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=sdk_config,
            )
            text = self._extract_text(response)
            logger.debug("generate() | response_len=%d", len(text))
            return text
        except GeminiServiceError:
            raise
        except Exception as exc:
            logger.error("generate() failed: %s", exc, exc_info=True)
            raise self._map_sdk_exception(exc) from exc

    def generate_with_context(
        self,
        prompt: str,
        context: str,
        **overrides: Any,
    ) -> str:
        """
        Single-shot generation with a prepended context block.

        The context is injected before the user prompt using a clear delimiter
        so the model can distinguish background information from the task.

        Parameters
        ----------
        prompt:
            The user's task / question.
        context:
            Background data or system state to inject before the prompt.
        **overrides:
            Optional ``GenerationConfig`` field overrides.

        Returns
        -------
        str
            The model's text response.
        """
        full_prompt = (
            f"=== CONTEXT ===\n{context}\n\n"
            f"=== TASK ===\n{prompt}"
        )
        logger.debug(
            "generate_with_context() | context_len=%d | prompt_len=%d",
            len(context),
            len(prompt),
        )
        return self.generate(full_prompt, **overrides)

    def generate_json(
        self,
        prompt: str,
        max_retries: int = _JSON_RETRY_ATTEMPTS,
        **overrides: Any,
    ) -> Any:
        """
        Generation with automatic JSON extraction and retry on malformed output.

        Instructs the model to return only JSON, attempts to parse the
        response, and retries up to ``max_retries`` times if parsing fails.

        Parameters
        ----------
        prompt:
            The prompt describing the desired JSON structure.
        max_retries:
            Number of generation+parse attempts before raising
            ``GeminiMalformedJSONError``.
        **overrides:
            Optional ``GenerationConfig`` field overrides.

        Returns
        -------
        Any
            The parsed Python object (``dict`` or ``list``).

        Raises
        ------
        GeminiMalformedJSONError
            If all retries are exhausted without producing valid JSON.
        """
        json_prompt = (
            f"{prompt}\n\n"
            "IMPORTANT: Respond with ONLY valid JSON. "
            "Do not include markdown fences, explanations, or any prose. "
            "The very first character of your response must be '{' or '['."
        )

        last_exc: Optional[Exception] = None
        last_text: str = ""

        for attempt in range(1, max_retries + 1):
            try:
                text = self.generate(json_prompt, **overrides)
                last_text = text
                result = self._parse_json(text)
                logger.debug(
                    "generate_json() succeeded on attempt %d / %d",
                    attempt,
                    max_retries,
                )
                return result
            except json.JSONDecodeError as exc:
                last_exc = exc
                logger.warning(
                    "generate_json() attempt %d / %d: JSON parse failed — %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    time.sleep(_JSON_RETRY_DELAY_S)
            except GeminiServiceError:
                raise  # Surface auth / quota / timeout immediately — no retry

        raise GeminiMalformedJSONError(
            f"generate_json() failed after {max_retries} attempt(s). "
            f"Last response: {last_text[:200]!r}",
            cause=last_exc,
        )

    def stream(self, prompt: str, **overrides: Any) -> Iterator[str]:
        """
        Yields text chunks as they arrive from the Gemini streaming API.

        Uses ``client.models.generate_content_stream()`` from the new SDK.
        Suitable for real-time UIs (e.g. Copilot chat with progressive
        rendering) to avoid waiting for the full response.

        Parameters
        ----------
        prompt:
            The complete prompt to send to the model.
        **overrides:
            Optional ``GenerationConfig`` field overrides.

        Yields
        ------
        str
            Successive text chunks as they are received.

        Raises
        ------
        GeminiServiceError (or a typed sub-class)
            If the stream cannot be initiated or encounters an error.
        """
        logger.debug("stream() | prompt_len=%d", len(prompt))
        try:
            client = self._get_client()
            sdk_config = self._build_sdk_config(overrides)
            response_stream = client.models.generate_content_stream(
                model=self._model_name,
                contents=prompt,
                config=sdk_config,
            )
            for chunk in response_stream:
                text = getattr(chunk, "text", None)
                if text:
                    yield text
        except GeminiServiceError:
            raise
        except Exception as exc:
            logger.error("stream() failed: %s", exc, exc_info=True)
            raise self._map_sdk_exception(exc) from exc

    # ------------------------------------------------------------------
    # Prompt builders  (pure functions — they do NOT call the API)
    # ------------------------------------------------------------------

    @staticmethod
    def build_summary_prompt(data: Dict[str, Any]) -> str:
        """
        Builds a prompt requesting an executive summary of network KPI data.

        Parameters
        ----------
        data:
            A dict of network metrics / KPIs to summarise.  The dict is
            serialised to JSON inside the prompt.

        Returns
        -------
        str
            A ready-to-use prompt string.  Call ``generate()`` with this.
        """
        serialised = json.dumps(data, indent=2, default=str)
        return (
            "You are an expert telecom network analyst.\n"
            "Analyse the following network performance data and produce a concise "
            "executive summary (3-5 sentences). Highlight critical issues, "
            "performance trends, and the top recommendation for the operator.\n\n"
            f"Network Data:\n{serialised}"
        )

    @staticmethod
    def build_recommendation_prompt(
        metrics: Dict[str, Any],
        predictions: List[float],
    ) -> str:
        """
        Builds a prompt requesting AI-driven optimisation recommendations.

        Parameters
        ----------
        metrics:
            Current network health metrics (throughput, latency, utilisation,
            etc.).
        predictions:
            List of near-term congestion forecast values (0.0 - 1.0) ordered
            by tower / time-step.

        Returns
        -------
        str
            A ready-to-use prompt string.
        """
        serialised_metrics = json.dumps(metrics, indent=2, default=str)
        serialised_preds = json.dumps(predictions, default=str)
        return (
            "You are PulseOS, an autonomous telecom optimisation AI.\n"
            "Given the current network metrics and short-term congestion predictions "
            "below, produce a prioritised list of at most 5 actionable "
            "recommendations in JSON format:\n"
            '[\n  {"priority": 1, "action": "...", "reason": "...", '
            '"estimated_impact": "..."},\n  ...\n]\n\n'
            f"Current Metrics:\n{serialised_metrics}\n\n"
            f"Congestion Predictions: {serialised_preds}"
        )

    @staticmethod
    def build_explanation_prompt(
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Builds a prompt requesting a plain-language explanation of an AI action
        (for the Explainable AI module).

        Parameters
        ----------
        action:
            The action or recommendation to explain (e.g.
            "THROTTLE_NON_ESSENTIAL on tower TW-042").
        context:
            Optional additional context dict (e.g. the metrics that triggered
            the recommendation).

        Returns
        -------
        str
            A ready-to-use prompt string.
        """
        ctx_block = ""
        if context:
            ctx_block = (
                f"\n\nContext that triggered this action:\n"
                f"{json.dumps(context, indent=2, default=str)}"
            )
        return (
            "You are PulseOS, explaining an autonomous network decision to a "
            "non-technical telecom operator.\n"
            "Explain the following AI-recommended action in plain language "
            "(2-3 sentences). Be specific about WHY this action was chosen "
            f"and what outcome it aims to achieve.\n\nAction: {action}{ctx_block}"
        )

    @staticmethod
    def build_chat_prompt(
        history: List[Dict[str, str]],
        user_message: str,
    ) -> str:
        """
        Builds a conversational chat prompt from a history of turns.

        Parameters
        ----------
        history:
            List of previous turns, each a dict with keys ``"role"``
            (``"user"`` | ``"assistant"``) and ``"content"``.
        user_message:
            The latest user message to append.

        Returns
        -------
        str
            A ready-to-use prompt string formatted as a chat transcript.

        Example
        -------
        >>> history = [
        ...     {"role": "user", "content": "What is the network status?"},
        ...     {"role": "assistant", "content": "All towers are healthy."},
        ... ]
        >>> GeminiService.build_chat_prompt(history, "Can you elaborate?")
        """
        lines: List[str] = [
            "You are PulseOS Copilot, a helpful AI assistant for telecom "
            "network operations. Continue the conversation below.\n"
        ]
        for turn in history:
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "").strip()
            lines.append(f"{role}: {content}")
        lines.append(f"User: {user_message}")
        lines.append("Assistant:")
        return "\n".join(lines)
