import asyncio
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edge_tts

from app.config import settings

_tts_executor = ThreadPoolExecutor(max_workers=1)


def _safe_slug(word: str) -> str:
    base = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff-]+", "_", word.strip())
    return (base[:40] or "sentence").strip("_")


def make_audio_filename(word: str) -> str:
    """ASCII-only filename for Anki [sound:…] and HTTP headers."""
    slug = _safe_slug(word)
    if slug.isascii():
        return f"jp_{slug}_example.mp3"
    digest = hashlib.sha1(word.encode("utf-8")).hexdigest()[:10]
    return f"jp_{digest}_example.mp3"


def zip_download_filename(word: str) -> str:
    name = make_audio_filename(word).replace(".mp3", "")
    return f"anki_{name}.zip"


async def _synthesize_edge(text: str, output_path: Path, voice: str) -> None:
    communicate = edge_tts.Communicate(text.strip(), voice)
    await communicate.save(str(output_path))


def _synthesize_gtts(text: str, output_path: Path) -> None:
    from gtts import gTTS

    tts = gTTS(text=text.strip(), lang="ja")
    tts.save(str(output_path))


async def synthesize_japanese(text: str, output_path: Path, voice: str | None = None) -> None:
    voice = voice or settings.tts_voice
    if settings.tts_prefer_gtts:
        _synthesize_gtts(text, output_path)
        return
    try:
        await _synthesize_edge(text, output_path, voice)
    except Exception:
        _synthesize_gtts(text, output_path)


def _run_async_tts(coro) -> None:
    """Run TTS coroutine even when called from inside uvicorn's event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    def _in_thread() -> None:
        asyncio.run(coro)

    _tts_executor.submit(_in_thread).result()


def synthesize_japanese_sync(text: str, output_path: Path, voice: str | None = None) -> None:
    _run_async_tts(synthesize_japanese(text, output_path, voice))
