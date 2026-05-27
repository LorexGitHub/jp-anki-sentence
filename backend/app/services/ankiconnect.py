from __future__ import annotations

import base64

import httpx

from app.config import settings
from app.models import CardPayload


def _anki_request(action: str, params: dict | None = None, timeout: float = 30.0) -> dict:
    body = {"action": action, "version": 6, "params": params or {}}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(settings.ankiconnect_url.rstrip("/"), json=body)
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"AnkiConnect error: {data['error']}")
        return data.get("result")


def _build_fields(card: CardPayload) -> dict:
    return {
        "Expression": card.sentence,
        "ExpressionFurigana": "",
        "ExpressionReading": card.sentence_reading,
        "ExpressionAudio": "",
        "SelectionText": "",
        "MainDefinition": card.sentence_meaning,
        "DefinitionPicture": "",
        "Sentence": "",
        "SentenceFurigana": "",
        "SentenceAudio": card.sentence_audio_tag,
        "Picture": "",
        "Glossary": card.sentence_reading,
        "Hint": "",
        "IsWordAndSentenceCard": "true",
        "IsClickCard": "",
        "IsSentenceCard": "false",
        "IsAudioCard": "true",
        "PitchPosition": "",
        "PitchCategories": "",
        "Frequency": "",
        "FreqSort": "",
        "MiscInfo": "",
    }


def add_card(card: CardPayload, audio_bytes: bytes) -> dict:
    _anki_request("storeMediaFile", {
        "filename": card.sentence_audio_filename,
        "data": base64.b64encode(audio_bytes).decode("ascii"),
    })

    return _anki_request("addNote", {
        "note": {
            "deckName": settings.anki_deck_name,
            "modelName": settings.anki_model_name,
            "fields": _build_fields(card),
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck",
            },
            "tags": ["jp-anki-sentence"],
        }
    })


def _store_media(card: CardPayload, audio_bytes: bytes) -> None:
    _anki_request("storeMediaFile", {
        "filename": card.sentence_audio_filename,
        "data": base64.b64encode(audio_bytes).decode("ascii"),
    })


def add_cards_batch(cards: list[tuple[CardPayload, bytes]]) -> dict:
    import logging
    logger = logging.getLogger(__name__)
    total_added = 0
    total_failed = 0
    CHUNK = 25

    for start in range(0, len(cards), CHUNK):
        chunk = cards[start:start + CHUNK]
        notes = []
        for card, audio_bytes in chunk:
            try:
                _store_media(card, audio_bytes)
            except Exception as exc:
                logger.warning("storeMediaFile failed for %s: %s", card.word, exc)
            notes.append({
                "deckName": settings.anki_deck_name,
                "modelName": settings.anki_model_name,
                "fields": _build_fields(card),
                "options": {
                    "allowDuplicate": True,
                },
                "tags": ["jp-anki-sentence"],
            })

        try:
            result = _anki_request("addNotes", {"notes": notes}, timeout=120.0)
            for i, r in enumerate(result):
                if r is None:
                    total_failed += 1
                    word = chunk[i][0].word if i < len(chunk) else "?"
                    logger.warning("addNotes failed for word=%s", word)
                else:
                    total_added += 1
        except Exception as exc:
            logger.warning("addNotes chunk failed: %s", exc)
            total_failed += len(notes)

    return {"added": total_added, "failed": total_failed}


def ping() -> bool:
    try:
        return bool(_anki_request("version"))
    except Exception:
        return False
