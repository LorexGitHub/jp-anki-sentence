import re

from app.config import settings
from app.services.hf_llm import is_hy_mt_model
from app.services.llm import LLMError, chat_text

SYSTEM_PROMPT = "You output short natural Japanese example sentences. Never explain, never add extra text."

USER_PROMPT_TEMPLATE = (
    "Write a short natural Japanese sentence using the word '{word}'. "
    "Output ONLY the sentence."
)

HY_MT_USER_PROMPT = (
    "Write a short natural Japanese sentence using the word '{word}'. "
    "Output ONLY the sentence."
)


def _build_prompt(word: str) -> tuple[str, str]:
    w = word.strip()
    if settings.llm_provider == "huggingface" and is_hy_mt_model():
        return "", HY_MT_USER_PROMPT.format(word=w)
    return SYSTEM_PROMPT, USER_PROMPT_TEMPLATE.format(word=w)


def _clean_sentence(raw: str) -> str:
    raw = raw.strip().strip('"').strip("'")
    raw = re.sub(r"^```[^\n]*\n?", "", raw)
    raw = re.sub(r"\n```$", "", raw)
    return raw.strip()


def _validate_word_in_sentence(word: str, sentence: str) -> None:
    nw = re.sub(r"\s+", "", word)
    ns = re.sub(r"\s+", "", sentence)
    if nw in ns:
        return
    if len(nw) >= 2:
        for i in range(len(nw), 1, -1):
            if nw[:i] in ns:
                return
    raise ValueError(f"Generated sentence does not contain target word '{word}'.")


def generate_sentence(word: str) -> str:
    system, user = _build_prompt(word)
    try:
        raw = chat_text(system, user)
    except LLMError:
        raise
    except Exception as exc:
        msg = str(exc).strip() or repr(exc)
        raise LLMError(f"LLM call failed: {msg}") from exc

    sentence = _clean_sentence(raw)
    if not sentence:
        raise ValueError("Model returned an empty sentence.")

    _validate_word_in_sentence(word.strip(), sentence)
    return sentence
