from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import genanki

from app.config import settings
from app.services.pipeline import build_card_bundle

logger = logging.getLogger(__name__)


def _find_model(models: dict, name_hint: str) -> tuple[int, dict] | None:
    for mid, model in models.items():
        if model.get("name", "").lower() == name_hint.lower():
            return int(mid), model
    for mid, model in models.items():
        if name_hint.lower() in model.get("name", "").lower():
            return int(mid), model
    return None


def _extract_notes(conn: sqlite3.Connection) -> tuple[dict, list[dict[str, Any]]]:
    col = conn.execute("SELECT models FROM col").fetchone()
    if not col:
        raise ValueError("No collection data found")
    models = json.loads(col[0])

    model_name = settings.anki_model_name

    # Debug: dump all model names with keys
    for mid, m in models.items():
        logger.info("Model id=%s name=%r", mid, m.get("name"))

    found = _find_model(models, model_name)
    if not found:
        available = [m.get("name", "?") for m in models.values()]
        logger.warning("Model '%s' not found. Available: %s", model_name, available)
        raise ValueError(
            f"Model '{model_name}' not found in deck. "
            f"Available models: {', '.join(available[:10])}"
        )

    model_id, lapis_model = found
    notes = conn.execute(
        "SELECT id, guid, flds, tags FROM notes WHERE mid = ?", (model_id,)
    ).fetchall()

    result = []
    for row in notes:
        fields = row["flds"].split("\x1f")
        result.append({
            "guid": row["guid"],
            "fields": list(fields),
            "tags": (row["tags"] or "").strip(),
        })
    return lapis_model, result


def process_apkg(file_bytes: bytes, progress: dict | None = None, control: dict | None = None) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            zf.extractall(tmp)

        col_src = tmp / "collection.anki21"
        if not col_src.exists():
            col_src = tmp / "collection.anki2"
        if not col_src.exists():
            raise ValueError("No collection file found")

        col_data = col_src.read_bytes()
        col_src.unlink()

        fd, col_path = tempfile.mkstemp(suffix=".anki2", prefix="_jpanki_")
        os.close(fd)
        Path(col_path).write_bytes(col_data)

        try:
            conn = sqlite3.connect(col_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=OFF")

            lapis_model, notes = _extract_notes(conn)

            # Extract actual deck ID from source collection
            col_row = conn.execute("SELECT decks FROM col").fetchone()
            source_decks: dict = json.loads(col_row[0]) if col_row else {}
            source_deck_id = None
            for did, d in source_decks.items():
                if d.get("name", "").lower() == settings.anki_deck_name.lower():
                    source_deck_id = int(did)
                    break
            if source_deck_id is None:
                # Fallback: deterministic hash of deck name
                source_deck_id = int(hashlib.sha256(settings.anki_deck_name.encode()).hexdigest()[:8], 16)

            conn.close()
        finally:
            try:
                os.unlink(col_path)
            except OSError:
                pass

        if not notes:
            raise ValueError("No Lapis notes found in deck")

        total = len(notes)
        audio_dir = tmp / "audio"
        audio_dir.mkdir(exist_ok=True)

        if progress is not None:
            progress["words"] = [
                (n["fields"][0] if n["fields"] else "").strip() or f"note_{n['guid']}"
                for n in notes
            ]
            progress["current_index"] = -1
            progress["results"] = {}
            progress["errors"] = {}
            progress["skipped"] = []

        genanki_model = genanki.Model(
            int(lapis_model["id"]),
            "Lapis",
            fields=[{"name": f["name"]} for f in lapis_model["flds"]],
            templates=[
                {
                    "name": t["name"],
                    "qfmt": t.get("qfmt", ""),
                    "afmt": t.get("afmt", ""),
                }
                for t in lapis_model.get("tmpls", [])
            ],
            css=lapis_model.get("css", ""),
        )

        genanki_deck = genanki.Deck(
            source_deck_id,
            settings.anki_deck_name,
        )

        media_files: list[str] = []

        for i, note in enumerate(notes):
            word = (note["fields"][0] if note["fields"] else "").strip()
            if not word:
                continue

            if progress is not None:
                progress["current_index"] = i

            # Handle skip-to and pause controls
            if control is not None:
                skip_to = control.get("skip_to")
                if skip_to is not None and i < skip_to:
                    if word not in progress.get("results", {}) and word not in progress.get("errors", {}):
                        progress.setdefault("skipped", []).append(word)
                    while len(note["fields"]) < 22:
                        note["fields"].append("")
                    try:
                        gnote = genanki.Note(
                            model=genanki_model,
                            fields=note["fields"],
                            tags=note["tags"],
                            guid=note["guid"] if note["guid"] else None,
                        )
                        genanki_deck.add_note(gnote)
                    except Exception as exc:
                        logger.warning("[%d/%d] %s -> genanki failed (%s)", i + 1, total, word, exc)
                    continue

                while control.get("paused", False):
                    time.sleep(0.5)
                    skip_to = control.get("skip_to")
                    if skip_to is not None and i < skip_to:
                        break

            try:
                bundle = build_card_bundle(word)
                card = bundle.card

                while len(note["fields"]) < 22:
                    note["fields"].append("")

                note["fields"][0] = card.sentence
                note["fields"][1] = ""
                note["fields"][2] = card.sentence_reading
                note["fields"][3] = ""
                note["fields"][5] = card.sentence_meaning
                note["fields"][7] = ""
                note["fields"][8] = ""
                note["fields"][9] = card.sentence_audio_tag
                note["fields"][11] = card.sentence_reading
                note["fields"][13] = "true"
                note["fields"][14] = ""

                audio_path = audio_dir / card.sentence_audio_filename
                audio_path.write_bytes(bundle.audio_bytes)
                media_files.append(str(audio_path))

                if progress is not None:
                    progress["results"][word] = {
                        "card": card.model_dump(),
                        "audio_bytes": bundle.audio_bytes,
                        "tsv": bundle.tsv,
                    }

                logger.info("[%d/%d] %s -> done", i + 1, total, word)
            except Exception as exc:
                logger.warning("[%d/%d] %s -> skipped (%s)", i + 1, total, word, exc)
                if progress is not None:
                    progress["errors"][word] = str(exc)

            try:
                gnote = genanki.Note(
                    model=genanki_model,
                    fields=note["fields"],
                    tags=note["tags"],
                    guid=note["guid"] if note["guid"] else None,
                )
                genanki_deck.add_note(gnote)
            except Exception as exc:
                logger.warning("[%d/%d] %s -> genanki failed (%s)", i + 1, total, word, exc)

        package = genanki.Package(genanki_deck)
        package.media_files = media_files

        output = io.BytesIO()
        package.write_to_file(output)
        return output.getvalue()
