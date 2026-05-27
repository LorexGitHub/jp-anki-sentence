# JP Anki Sentence Generator

Generate Japanese example sentences for Anki (Lapis note type). Upload an `.apkg`, batch-process all words with sentence + reading + translation + audio, download the updated `.apkg`.

## Requirements

- Python 3.11+, Node.js 18+
- ~2 GB free disk

## Setup

```powershell
cd backend && python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt
cd frontend && npm install
```

## Run

```powershell
# Terminal 1
cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend && npm run dev
```

Open http://localhost:5173

## `.env`

| Variable | Default |
|----------|---------|
| `HF_MODEL_ID` | `Qwen/Qwen2.5-0.5B-Instruct` |
| `ANKI_DECK_NAME` | `日本語の文` |
| `ANKI_MODEL_NAME` | `Lapis` |

## Pipeline

Tatoeba API (common words) → Qwen 0.5B (rare words fallback) → opus-mt-ja-en (translation) → pykakasi (readings) → gTTS (audio)

## API

| Endpoint | Purpose |
|----------|---------|
| `POST /api/generate` | Generate card for a word |
| `POST /api/add-to-anki` | Add word to Anki via AnkiConnect |
| `POST /api/add-to-anki/batch` | Batch-add words |
| `POST /api/upload-apkg` | Upload `.apkg` for batch processing |
| `GET /api/task/{id}` | Batch progress |
| `POST /api/task/{id}/control` | Pause/resume/skip |
| `GET /api/task/{id}/download` | Download processed `.apkg` |

## Batch usage

1. Anki → File → Export → `.apkg`
2. Upload on web UI → process → **Add All Passed** or **Download .apkg**
3. Click word numbers to skip, Pause/Go to control
