import csv
import io
import zipfile
from pathlib import Path

from app.models import CardPayload

# UTF-8 BOM helps Anki/Excel recognize encoding on Windows
UTF8_BOM = "\ufeff"

ANKI_HEADERS = [
    "Expression",
    "ExpressionFurigana",
    "ExpressionReading",
    "ExpressionAudio",
    "SelectionText",
    "MainDefinition",
    "DefinitionPicture",
    "Sentence",
    "SentenceFurigana",
    "SentenceAudio",
    "Picture",
    "Glossary",
    "Hint",
    "IsWordAndSentenceCard",
    "IsClickCard",
    "IsSentenceCard",
    "IsAudioCard",
    "PitchPosition",
    "PitchCategories",
    "Frequency",
    "FreqSort",
    "MiscInfo",
]


def build_card_payload(
    word: str,
    data: dict,
    audio_filename: str,
) -> CardPayload:
    audio_tag = f"[sound:{audio_filename}]"
    w = word.strip()
    wr = data.get("word_reading", "").strip()
    return CardPayload(
        word=w,
        word_reading=wr,
        word_meaning=data.get("word_meaning", "").strip(),
        expression_furigana=data.get("expression_furigana", f"{w}[{wr}]").strip(),
        sentence=data.get("sentence", "").strip(),
        sentence_bold=data.get("sentence_bold", data.get("sentence", "")).strip(),
        sentence_anki=data.get("sentence_anki", "").strip(),
        sentence_reading=data.get("sentence_reading", "").strip(),
        sentence_meaning=data.get("sentence_meaning", "").strip(),
        context_note=data.get("context_note", "").strip(),
        sentence_audio_filename=audio_filename,
        sentence_audio_tag=audio_tag,
    )


def card_to_tsv_row(card: CardPayload) -> list[str]:
    return [
        card.sentence,
        "",
        card.sentence_reading,
        "",
        "",
        card.sentence_meaning,
        "",
        "",
        "",
        card.sentence_audio_tag,
        "",
        card.sentence_reading,
        "",
        "true",
        "",
        "false",
        "true",
        "",
        "",
        "",
        "",
        "",
    ]


def build_tsv(card: CardPayload) -> str:
    buffer = io.StringIO()
    buffer.write(UTF8_BOM)
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(ANKI_HEADERS)
    writer.writerow(card_to_tsv_row(card))
    return buffer.getvalue()


def build_zip_bytes(card: CardPayload, audio_path: Path, tsv: str | None = None) -> bytes:
    tsv = tsv if tsv is not None else build_tsv(card)
    readme = f"""# Anki import — {card.word}

TSV columns match the Migaku Japanese note type. Import directly without remapping.

## Audio
- Filename: {card.sentence_audio_filename}
- Tag in TSV: {card.sentence_audio_tag}
"""

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("anki_import.tsv", tsv.encode("utf-8"))
        zf.writestr("README.txt", readme.encode("utf-8"))
        if audio_path.exists():
            zf.write(audio_path, arcname=card.sentence_audio_filename)
    return zip_buffer.getvalue()


IMPORT_NOTES = [
    "TSV columns match the Migaku Japanese note type — import directly without remapping.",
    "ExpressionFurigana uses Anki format: 漢字[かんじ].",
    "SentenceFurigana uses Anki format: 漢字[かんじ].",
    "Audio files are embedded in the ZIP.",
]
