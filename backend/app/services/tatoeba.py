import logging
import re

import httpx

logger = logging.getLogger(__name__)

TATOEBA_API = "https://api.tatoeba.org/v1/sentences"
TIMEOUT = 10


def _extract_english(translations: list) -> str | None:
    for t in translations:
        if isinstance(t, dict) and t.get("lang") == "eng":
            text = (t.get("text") or "").strip()
            if text:
                return text
    return None


def _word_in_sentence(word: str, sentence: str) -> bool:
    nw = re.sub(r"\s+", "", word)
    ns = re.sub(r"\s+", "", sentence)
    if nw in ns:
        return True
    if len(nw) >= 2:
        for i in range(len(nw), 1, -1):
            if nw[:i] in ns:
                return True
    return False


def search(word: str) -> tuple[str, str] | None:
    """Search Tatoeba for a Japanese sentence + English translation.
    Returns (sentence, translation) or None.
    """
    params = {
        "lang": "jpn",
        "q": word,
        "sort": "words",
        "limit": 10,
        "showtrans": "all",
    }
    try:
        r = httpx.get(TATOEBA_API, params=params, timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as exc:
        logger.warning("Tatoeba API error: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Tatoeba request failed: %s", exc)
        return None

    results = data.get("data", [])
    if not results:
        return None

    candidates: list[tuple[str, str]] = []
    for s in results:
        jp = (s.get("text") or "").strip()
        if not jp:
            continue
        if not _word_in_sentence(word, jp):
            continue
        en = _extract_english(s.get("translations", []))
        if not en:
            continue
        candidates.append((jp, en))

    if not candidates:
        return None

    # Pick the shortest sentence that clearly contains the word
    candidates.sort(key=lambda x: len(x[0]))
    return candidates[0]
