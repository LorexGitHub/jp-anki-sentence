from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class LLMError(Exception):
    pass


def _ollama_base() -> str:
    return settings.ollama_base_url.rstrip("/")


def _openai_base() -> str:
    return settings.llm_base_url.rstrip("/")


def _active_model() -> str:
    if settings.llm_provider == "ollama":
        return settings.ollama_model
    return settings.llm_model


def check_llm_status() -> dict[str, Any]:
    if settings.llm_provider == "huggingface":
        from app.services.hf_llm import check_huggingface_status

        return check_huggingface_status()
    if settings.llm_provider == "ollama":
        return _check_ollama_status()
    return _check_openai_compatible_status()


def _check_ollama_status() -> dict[str, Any]:
    base = _ollama_base()
    model = settings.ollama_model
    result: dict[str, Any] = {
        "provider": "ollama",
        "base_url": base,
        "model": model,
        "server_running": False,
        "model_available": False,
        "available_models": [],
        "setup_hint": None,
        "ollama_mlx_crash_note": (
            "If `ollama` crashes with Exception 0xc0000005, use LM Studio instead: "
            "set LLM_PROVIDER=openai_compatible in .env (see README)."
        ),
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            tags = client.get(f"{base}/api/tags")
            tags.raise_for_status()
            payload = tags.json()
    except httpx.ConnectError:
        result["setup_hint"] = (
            "Ollama is not running. Start the Ollama app, or switch to LM Studio: "
            "LLM_PROVIDER=openai_compatible in .env"
        )
        return result
    except httpx.HTTPError as exc:
        result["setup_hint"] = f"Cannot reach Ollama at {base}: {exc}"
        return result

    result["server_running"] = True
    names = [m.get("name", "") for m in payload.get("models", [])]
    result["available_models"] = names
    result["model_available"] = _model_name_matches(names, model)
    if not result["model_available"]:
        result["setup_hint"] = f'Model "{model}" not found. Run: ollama pull {model}'
    return result


def _check_openai_compatible_status() -> dict[str, Any]:
    base = _openai_base()
    model = settings.llm_model
    result: dict[str, Any] = {
        "provider": "openai_compatible",
        "base_url": base,
        "model": model,
        "server_running": False,
        "model_available": False,
        "available_models": [],
        "setup_hint": None,
        "ollama_mlx_crash_note": None,
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{base}/models",
                headers=_auth_headers(),
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.ConnectError:
        result["setup_hint"] = (
            "Local LLM server not reachable. Install LM Studio (https://lmstudio.ai), "
            "load a model (e.g. Qwen2.5-7B-Instruct), then Developer → Start Server "
            "(default http://127.0.0.1:1234)."
        )
        return result
    except httpx.HTTPError as exc:
        result["setup_hint"] = f"Cannot reach LLM server at {base}: {exc}"
        return result

    result["server_running"] = True
    names = [m.get("id", "") for m in payload.get("data", [])]
    result["available_models"] = names

    if not names:
        # Some servers omit /models until a model is loaded; allow try anyway.
        result["model_available"] = True
        result["setup_hint"] = (
            "Server is up. Load a model in LM Studio and set LLM_MODEL to the name "
            "shown under the server tab."
        )
    else:
        result["model_available"] = _model_name_matches(names, model) or model == "local-model"
        if not result["model_available"]:
            result["setup_hint"] = (
                f'Model "{model}" not in server list. Set LLM_MODEL in .env to one of: '
                f"{', '.join(names[:5])}"
            )
    return result


def _model_name_matches(available: list[str], wanted: str) -> bool:
    wanted_l = wanted.lower()
    for name in available:
        n = name.lower()
        if n == wanted_l or n.startswith(f"{wanted_l}:") or wanted_l in n:
            return True
    base = wanted.split(":")[0].lower()
    return any(base in n.lower() for n in available)


def _auth_headers() -> dict[str, str]:
    key = settings.llm_api_key.strip()
    if key and key != "not-needed":
        return {"Authorization": f"Bearer {key}"}
    return {}


def chat_json(system: str, user: str) -> str:
    if settings.llm_provider == "huggingface":
        from app.services.hf_llm import chat_json as hf_chat_json

        status = check_llm_status()
        if not status["server_running"]:
            raise LLMError(status["setup_hint"] or "Hugging Face backend not ready.")
        return hf_chat_json(system, user)

    status = check_llm_status()
    if not status["server_running"]:
        raise LLMError(status["setup_hint"] or "LLM server is not running.")
    if not status["model_available"] and status.get("setup_hint"):
        if status["available_models"]:
            raise LLMError(status["setup_hint"])

    if settings.llm_provider == "ollama":
        return _chat_ollama(system, user)
    return _chat_openai_compatible(system, user)


def chat_text(system: str, user: str) -> str:
    """Like chat_json but without enforcing JSON output format — for free-text generation."""
    if settings.llm_provider == "huggingface":
        from app.services.hf_llm import chat_json as hf_chat_json

        status = check_llm_status()
        if not status["server_running"]:
            raise LLMError(status["setup_hint"] or "Hugging Face backend not ready.")
        return hf_chat_json(system, user)

    status = check_llm_status()
    if not status["server_running"]:
        raise LLMError(status["setup_hint"] or "LLM server is not running.")
    if not status["model_available"] and status.get("setup_hint"):
        if status["available_models"]:
            raise LLMError(status["setup_hint"])

    if settings.llm_provider == "ollama":
        return _chat_ollama_text(system, user)
    return _chat_openai_text(system, user)


def _chat_ollama_text(system: str, user: str) -> str:
    base = _ollama_base()
    body = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.7},
    }
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(f"{base}/api/chat", json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc
    content = (payload.get("message") or {}).get("content") or ""
    return _require_content(content, "Ollama")


def _chat_openai_text(system: str, user: str) -> str:
    base = _openai_base()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    body: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.7,
    }
    content = _post_chat_completions(base, body)
    return _require_content(content, "LLM server")


def _chat_ollama(system: str, user: str) -> str:
    base = _ollama_base()
    body = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.7},
    }
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(f"{base}/api/chat", json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc

    content = (payload.get("message") or {}).get("content") or ""
    return _require_content(content, "Ollama")


def _chat_openai_compatible(system: str, user: str) -> str:
    base = _openai_base()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    body: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }

    try:
        content = _post_chat_completions(base, body)
    except LLMError:
        body.pop("response_format", None)
        content = _post_chat_completions(base, body)

    return _require_content(content, "LLM server")


def _post_chat_completions(base: str, body: dict[str, Any]) -> str:
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(
                f"{base}/chat/completions",
                json=body,
                headers=_auth_headers(),
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.ConnectError as exc:
        raise LLMError(
            f"Cannot reach {base}. Start LM Studio server or check LLM_BASE_URL."
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:400] if exc.response else str(exc)
        raise LLMError(f"LLM request failed ({exc.response.status_code}): {detail}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise LLMError("LLM returned no choices.")
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


def _require_content(content: str, source: str) -> str:
    text = (content or "").strip()
    if not text:
        raise LLMError(f"{source} returned an empty response.")
    return text


# Backwards compatibility for imports
OllamaError = LLMError
