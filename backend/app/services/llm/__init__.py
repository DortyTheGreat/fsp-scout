"""Провайдеры LLM. Персональные данные не уходят за пределы контура: модель локальная (llama.cpp
llama-server, Ollama, vLLM, LM Studio — любой OpenAI-совместимый сервер); режим none — без LLM, всё работает
на правилах.

Интерфейс один: chat_json(system, user, schema) → dict | None. None означает «LLM недоступна» —
вызывающий код обязан иметь запасной путь на правилах.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from app.core.config import settings

log = logging.getLogger("llm")


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # рассуждающие модели (Qwen3 и др.)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


class NoLLM:
    name = "none"

    def chat_json(self, system: str, user: str, schema: dict | None = None, timeout_s: float | None = None) -> dict | None:
        return None

    def chat(self, system: str, user: str, timeout_s: float | None = None) -> str | None:
        return None


class OpenAICompatLLM:
    """Любой OpenAI-совместимый сервер: llama.cpp (llama-server, base_url=http://host:8080/v1),
    Ollama (base_url=http://ollama:11434/v1, model=qwen2.5:3b), vLLM, LM Studio."""
    name = "openai"

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout_s: float | None = None):
        self.model = model or settings.llm_model
        self.http = httpx.Client(base_url=(base_url or settings.llm_base_url).rstrip("/"),
                                 timeout=timeout_s or settings.llm_timeout_s,
                                 headers={"Authorization": f"Bearer {settings.llm_api_key}"})
        self.json_mode_supported = True

    def _post(self, messages: list[dict], json_mode: bool, timeout_s: float | None = None) -> dict:
        """Один запрос; исключения пробрасываются. Возвращает ответ сервера целиком (с usage/timings).
        timeout_s — для запросов, которые ждёт пользователь (короче, чем для фоновых)."""
        timeout = timeout_s if timeout_s else httpx.USE_CLIENT_DEFAULT
        body = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": settings.llm_max_tokens}
        if settings.llm_disable_thinking:  # llama.cpp / vLLM: отключить режим рассуждений (Qwen3 и др.)
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if json_mode and self.json_mode_supported:
            body["response_format"] = {"type": "json_object"}
        r = self.http.post("/chat/completions", json=body, timeout=timeout)
        if r.status_code == 400 and "response_format" in body:
            # сервер не умеет JSON-режим — повторяем без него, JSON достанем из текста
            self.json_mode_supported = False
            body.pop("response_format")
            r = self.http.post("/chat/completions", json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def _complete(self, messages: list[dict], json_mode: bool, timeout_s: float | None = None) -> str | None:
        try:
            return self._post(messages, json_mode, timeout_s)["choices"][0]["message"]["content"]
        except Exception as e:  # сеть, таймаут, неподдерживаемый формат — уходим на правила
            log.warning("LLM error: %s", e)
            return None

    @staticmethod
    def json_messages(system: str, user: str, schema: dict | None) -> list[dict]:
        sys = system + ("\nОтвечай строго одним JSON-объектом по схеме:\n" + json.dumps(schema, ensure_ascii=False)
                        if schema else "\nОтвечай строго одним JSON-объектом.")
        return [{"role": "system", "content": sys}, {"role": "user", "content": user}]

    def chat_json(self, system: str, user: str, schema: dict | None = None, timeout_s: float | None = None) -> dict | None:
        return _extract_json(self._complete(self.json_messages(system, user, schema), True, timeout_s) or "")

    def chat(self, system: str, user: str, timeout_s: float | None = None) -> str | None:
        return self._complete([{"role": "system", "content": system}, {"role": "user", "content": user}], False,
                              timeout_s)


_llm = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = {"openai": OpenAICompatLLM, "ollama": OpenAICompatLLM, "llamacpp": OpenAICompatLLM}.get(
            settings.llm_provider, NoLLM)()
    return _llm


def set_llm(llm) -> None:
    global _llm
    _llm = llm
