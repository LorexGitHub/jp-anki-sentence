"""Shared generate + TTS + export pipeline."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.services.anki_export import build_card_payload, build_tsv, build_zip_bytes
from app.services.card_cache import CardBundle, get as cache_get, put as cache_put
from app.services.readings import build_furigana, sentence_reading, word_reading
from app.services.sentence import generate_sentence
from app.services.tatoeba import search as tatoeba_search
from app.services.translator import translate
from app.services.tts import make_audio_filename, synthesize_japanese_sync

logger = logging.getLogger(__name__)


def _bold_word_in_sentence(sentence: str, word: str) -> str:
    w = word.strip()
    s = sentence.strip()
    if w in s:
        return s.replace(w, f"<b>{w}</b>", 1)
    return s


def _build_from_sentence(key: str, sentence: str, sentence_meaning: str) -> CardBundle:
    """Given a sentence + translation, extract readings, TTS, and assemble the card."""
    expression_furigana = build_furigana(key)
    sentence_furigana = build_furigana(sentence)
    sentence_reading_kana = sentence_reading(sentence)
    word_reading_kana = word_reading(key)
    sentence_bold = _bold_word_in_sentence(sentence, key)
    audio_filename = make_audio_filename(key)

    data = {
        "word_reading": word_reading_kana,
        "word_meaning": "",
        "expression_furigana": expression_furigana,
        "sentence": sentence,
        "sentence_bold": sentence_bold,
        "sentence_anki": sentence_furigana,
        "sentence_reading": sentence_reading_kana,
        "sentence_meaning": sentence_meaning,
        "context_note": "",
    }

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = Path(tmp) / audio_filename
        synthesize_japanese_sync(sentence, audio_path)
        audio_bytes = audio_path.read_bytes()
        card = build_card_payload(key, data, audio_filename)
        tsv = build_tsv(card)
        zip_bytes = build_zip_bytes(card, audio_path, tsv=tsv)

    return CardBundle(
        data=data,
        card=card,
        audio_bytes=audio_bytes,
        tsv=tsv,
        zip_bytes=zip_bytes,
    )


def build_card_bundle(word: str, *, use_cache: bool = True) -> CardBundle:
    key = word.strip()
    if use_cache:
        cached = cache_get(key)
        if cached is not None:
            return cached

    # 1) Try Tatoeba (real native sentence, already translated)
    tatoeba_result = tatoeba_search(key)
    if tatoeba_result is not None:
        sentence, translation = tatoeba_result
        logger.info("Tatoeba hit for %r", key)
        bundle = _build_from_sentence(key, sentence, translation)
        cache_put(key, bundle)
        return bundle

    # 2) Fallback: LLM sentence generation + opus-mt translation
    logger.info("Tatoeba miss for %r — using LLM fallback", key)
    sentence = generate_sentence(key)
    sentence_meaning = translate(sentence)
    bundle = _build_from_sentence(key, sentence, sentence_meaning)
    cache_put(key, bundle)
    return bundle
