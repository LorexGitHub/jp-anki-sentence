from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=64, description="Japanese word or expression")


class CardPayload(BaseModel):
    word: str
    word_reading: str
    word_meaning: str
    expression_furigana: str
    sentence: str
    sentence_bold: str
    sentence_anki: str
    sentence_reading: str
    sentence_meaning: str
    context_note: str
    sentence_audio_filename: str
    sentence_audio_tag: str


class GenerateResponse(BaseModel):
    card: CardPayload
    anki_tsv: str
    import_notes: list[str]
    sentence_audio_base64: str


class AddToAnkiRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=64)


class AddToAnkiResponse(BaseModel):
    success: bool
    note_id: int | None = None


class TaskControlRequest(BaseModel):
    action: str  # "pause", "resume", "skip"
    index: int | None = None


class AddBatchRequest(BaseModel):
    words: list[str]
