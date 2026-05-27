"""In-memory cache so Download ZIP is instant after Generate."""

from __future__ import annotations

from dataclasses import dataclass

from app.models import CardPayload


@dataclass
class CardBundle:
    data: dict
    card: CardPayload
    audio_bytes: bytes
    tsv: str
    zip_bytes: bytes


_cache: dict[str, CardBundle] = {}


def get(word: str) -> CardBundle | None:
    return _cache.get(word.strip())


def put(word: str, bundle: CardBundle) -> None:
    _cache[word.strip()] = bundle


def clear() -> None:
    _cache.clear()
