"""Run a Hugging Face model in-process; weights auto-download on first use."""

from __future__ import annotations

import importlib.util
import logging
import os
import threading
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)
from app.services.llm import LLMError

_lock = threading.Lock()
_model: Any = None
_tokenizer: Any = None
_loading = False
_loaded_model_id: str | None = None


def is_hy_mt_model(model_id: str | None = None) -> bool:
    mid = (model_id or settings.hf_model_id).lower()
    return "hy-mt" in mid or "hy_mt" in mid


def _deps_available() -> bool:
    """Fast check without importing torch (import can take 30+ seconds)."""
    return (
        importlib.util.find_spec("torch") is not None
        and importlib.util.find_spec("transformers") is not None
    )


def _hf_hub_cache_dir() -> Path:
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def is_model_cached(model_id: str | None = None) -> bool:
    """Fast local cache check — no network, no full snapshot_download scan."""
    model_id = model_id or settings.hf_model_id
    repo_dir = _hf_hub_cache_dir() / f"models--{model_id.replace('/', '--')}"
    snapshots = repo_dir / "snapshots"
    if not snapshots.is_dir():
        return False
    for snap in snapshots.iterdir():
        if not snap.is_dir():
            continue
        has_config = (snap / "config.json").is_file()
        has_weights = any(snap.glob("*.safetensors")) or any(snap.glob("*.bin"))
        if has_config and has_weights:
            return True
    return False


def _size_hint(model_id: str) -> str:
    mid = model_id.lower()
    if "1.8b" in mid:
        return "~4 GB"
    if "0.5b" in mid:
        return "~1 GB"
    if "1.5b" in mid:
        return "~3 GB"
    if "7b" in mid:
        return "~14 GB"
    return "several GB"


def check_huggingface_status() -> dict[str, Any]:
    model_id = settings.hf_model_id
    result: dict[str, Any] = {
        "provider": "huggingface",
        "base_url": f"https://huggingface.co/{model_id}",
        "model": model_id,
        "server_running": False,
        "model_available": False,
        "available_models": [model_id],
        "setup_hint": None,
        "ollama_mlx_crash_note": None,
        "model_cached": False,
        "model_family": "hy-mt2" if is_hy_mt_model(model_id) else "generic",
        "model_loading": _loading,
        "model_loaded_in_memory": _model is not None and _loaded_model_id == model_id,
    }

    if not _deps_available():
        result["setup_hint"] = (
            "Hugging Face dependencies missing. In backend venv run: "
            "pip install -r requirements.txt"
        )
        return result

    result["server_running"] = True
    result["model_available"] = True
    cached = is_model_cached(model_id)
    result["model_cached"] = cached

    if _loading:
        result["setup_hint"] = "Loading model into memory — first card may take a few minutes…"
    elif result["model_loaded_in_memory"]:
        result["setup_hint"] = "Model loaded — ready to generate."
    elif not cached:
        result["setup_hint"] = (
            f"First generate downloads {_size_hint(model_id)} from Hugging Face, then caches locally."
        )
    else:
        result["setup_hint"] = "Model cached on disk — click Generate (loads into memory once per server run)."
    return result


def _load_model() -> tuple[Any, Any]:
    global _model, _tokenizer, _loading, _loaded_model_id

    model_id = settings.hf_model_id
    if _model is not None and _tokenizer is not None and _loaded_model_id == model_id:
        return _model, _tokenizer

    with _lock:
        if _model is not None and _tokenizer is not None and _loaded_model_id == model_id:
            return _model, _tokenizer

        if not _deps_available():
            raise LLMError(
                "Install HF deps: pip install -r requirements.txt"
            )

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        _loading = True
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if is_hy_mt_model(model_id):
                dtype = torch.bfloat16 if device == "cuda" else torch.float32
            else:
                dtype = torch.float16 if device == "cuda" else torch.float32

            _tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
            load_kwargs: dict[str, Any] = {
                "dtype": dtype,
                "trust_remote_code": True,
            }
            attn = settings.hf_attn_implementation
            if attn != "eager":
                load_kwargs["attn_implementation"] = attn
            if device == "cuda":
                load_kwargs["device_map"] = "auto"
            else:
                load_kwargs["low_cpu_mem_usage"] = True

            try:
                _model = AutoModelForCausalLM.from_pretrained(model_id, **load_kwargs)
            except Exception:
                if attn != "eager":
                    logger.warning("Attention implementation '%s' failed, falling back to eager", attn)
                    load_kwargs["attn_implementation"] = "eager"
                    _model = AutoModelForCausalLM.from_pretrained(model_id, **load_kwargs)
                else:
                    raise
            if device == "cpu":
                _model = _model.to(device)
            _model.eval()
            _loaded_model_id = model_id
        finally:
            _loading = False

        return _model, _tokenizer


def _model_device(model: Any) -> Any:
    return next(model.parameters()).device


def _move_inputs_to_device(inputs: Any, device: Any) -> Any:
    """Move tokenizer outputs (tensor, dict, or BatchEncoding) to the model device."""
    if hasattr(inputs, "items"):
        return {key: value.to(device) for key, value in inputs.items()}
    if hasattr(inputs, "to"):
        return inputs.to(device)
    raise LLMError(f"Unexpected tokenizer output type: {type(inputs).__name__}")


def _input_token_length(inputs: Any) -> int:
    if hasattr(inputs, "get"):
        ids = inputs.get("input_ids")
        if ids is not None:
            return int(ids.shape[-1])
    if hasattr(inputs, "input_ids"):
        return int(inputs.input_ids.shape[-1])
    if hasattr(inputs, "shape"):
        return int(inputs.shape[-1])
    raise LLMError("Could not determine prompt length from model inputs.")


def _generate(model: Any, tokenizer: Any, inputs: Any) -> str:
    import torch

    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": settings.hf_max_new_tokens,
        "temperature": 0.7,
        "do_sample": True,
        "pad_token_id": tokenizer.eos_token_id or tokenizer.pad_token_id,
    }

    if is_hy_mt_model():
        gen_kwargs.update(
            top_p=0.6,
            top_k=20,
            repetition_penalty=1.05,
        )
    else:
        gen_kwargs.setdefault("top_p", 0.9)

    generate_inputs = inputs if hasattr(inputs, "items") else {"input_ids": inputs}
    input_len = _input_token_length(generate_inputs)

    with torch.inference_mode():
        output_ids = model.generate(**generate_inputs, **gen_kwargs)

    new_tokens = output_ids[0, input_len:]
    text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    if not text:
        raise LLMError("Hugging Face model returned an empty response.")
    return text


def chat_json(system: str, user: str) -> str:
    model, tokenizer = _load_model()

    if is_hy_mt_model():
        parts = [p for p in (system.strip(), user.strip()) if p]
        prompt = "\n\n".join(parts)
        messages = [{"role": "user", "content": prompt}]
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
        )
        inputs = _move_inputs_to_device(inputs, _model_device(model))
        return _generate(model, tokenizer, inputs)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    else:
        prompt = f"{system}\n\nUser: {user}\n\nAssistant:"

    tokenized = tokenizer(prompt, return_tensors="pt")
    tokenized = _move_inputs_to_device(tokenized, _model_device(model))
    return _generate(model, tokenizer, tokenized)
