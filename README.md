# JP Anki Sentence Generator

Generate Japanese example sentences for Anki (Lapis note type). Upload `.apkg`, batch-process all words with sentence + reading + translation + audio, download updated `.apkg`.

## Run

```powershell
# Terminal 1
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend; npm run dev
```

Open http://localhost:5173

## First-time setup

```powershell
cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
cd frontend; npm install
```

## `.env`

```
LLM_PROVIDER=huggingface
HF_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
ANKI_DECK_NAME=日本語の文
ANKI_MODEL_NAME=Lapis
```

## Pipeline

Tatoeba API (common words) → Qwen 0.5B (rare words) → opus-mt-ja-en (translation) → pykakasi (readings) → gTTS (audio)
