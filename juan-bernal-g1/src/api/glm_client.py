from __future__ import annotations

import asyncio
import json
import re
import time
import logging
from typing import Any, Optional

import httpx

from src import config

logger = logging.getLogger(__name__)


class GLMError(Exception):
    pass


class GLMTimeoutError(GLMError):
    pass


class GLMResponseParseError(GLMError):
    pass


def extract_json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        candidate = json_match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            for end in range(len(candidate), 0, -1):
                try:
                    return json.loads(candidate[:end])
                except json.JSONDecodeError:
                    continue

    raise GLMResponseParseError(f"No se pudo extraer JSON valido de la respuesta: {text[:200]}...")


class GLMClient:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        timeout: int = 0,
        max_retries: int = 0,
        temperature: float = 0,
        max_tokens: int = 0,
    ):
        self.api_key = api_key or config.GLM_API_KEY
        self.base_url = (base_url or config.GLM_API_BASE_URL).rstrip("/")
        self.model = model or config.GLM_MODEL
        self.timeout = timeout or config.GLM_TIMEOUT
        self.max_retries = max_retries or config.GLM_MAX_RETRIES
        self.temperature = temperature if temperature else config.GLM_TEMPERATURE
        self.max_tokens = max_tokens or config.GLM_MAX_TOKENS
        self._last_call_time: float = 0.0
        self._min_interval = 1.0 / config.RATE_LIMIT_RPS

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }

    async def _rate_limit(self) -> None:
        if self._last_call_time > 0:
            elapsed = time.monotonic() - self._last_call_time
            wait = self._min_interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_call_time = time.monotonic()

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        payload = self._build_payload(system_prompt, user_prompt)
        url = f"{self.base_url}/chat/completions"
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                await self._rate_limit()
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=self._headers(), json=payload)

                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("Rate limit (429), esperando %ss (intento %d)", wait, attempt)
                    await asyncio.sleep(wait)
                    last_error = GLMError(f"Rate limited (intento {attempt})")
                    continue

                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = extract_json_from_text(content)
                logger.info("GLM call exitosa en intento %d", attempt)
                return parsed

            except httpx.TimeoutException as e:
                last_error = GLMTimeoutError(str(e))
                wait = 2 ** (attempt - 1)
                logger.warning("Timeout en intento %d, esperando %ss", attempt, wait)
                await asyncio.sleep(wait)

            except (httpx.HTTPStatusError, httpx.HTTPError) as e:
                last_error = GLMError(str(e))
                wait = 2 ** (attempt - 1)
                logger.warning("Error HTTP en intento %d: %s, esperando %ss", attempt, e, wait)
                await asyncio.sleep(wait)

            except GLMResponseParseError as e:
                last_error = e
                wait = 2 ** (attempt - 1)
                logger.warning("Error de parseo en intento %d: %s, esperando %ss", attempt, e, wait)
                await asyncio.sleep(wait)

            except (KeyError, IndexError) as e:
                last_error = GLMResponseParseError(f"Respuesta inesperada: {e}")
                wait = 2 ** (attempt - 1)
                logger.warning("Estructura inesperada en intento %d, esperando %ss", attempt, wait)
                await asyncio.sleep(wait)

        raise last_error or GLMError("Todos los intentos fallaron")

    async def call_raw(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[dict[str, Any] | None, int, str | None]:
        payload = self._build_payload(system_prompt, user_prompt)
        url = f"{self.base_url}/chat/completions"
        last_error: Optional[str] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                await self._rate_limit()
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=self._headers(), json=payload)

                if resp.status_code == 429:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    last_error = f"Rate limited (intento {attempt})"
                    continue

                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = extract_json_from_text(content)
                return parsed, attempt, None

            except Exception as e:
                last_error = str(e)
                wait = 2 ** (attempt - 1)
                await asyncio.sleep(wait)

        return None, self.max_retries, last_error
