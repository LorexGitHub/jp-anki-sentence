# JP Anki Sentence Generator

Generate natural Japanese example sentences for vocabulary study, with **Anki-ready furigana**, **example audio**, and a **one-file import ZIP**.

**Default:** downloads and runs **[Tencent Hy-MT2-1.8B](https://huggingface.co/tencent/Hy-MT2-1.8B)** from Hugging Face on first use — no LM Studio, no Ollama, no API key. Hy-MT2 is Tencent’s multilingual translation model with strong Japanese support.

## Features

- Enter a word like `元気` and get a short, conversational example sentence
- **Hugging Face model** auto-downloads into `~/.cache/huggingface` (~3 GB once)
- Furigana in Anki format: `元気[げんき]`
- TTS audio (Edge / gTTS fallback)
- Anki ZIP import (TSV + MP3)

## Requirements

- Python 3.11+
- Node.js 18+
- ~4 GB free disk (model cache + dependencies)
- 8 GB RAM minimum recommended for the 1.5B model on CPU

---

## Quick start (Hugging Face — recommended)

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Optional: pre-download the model (otherwise it downloads on first **Generate**):

```powershell
python scripts\download_model.py
```

Run API:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — first generation may take several minutes while the model downloads and loads.

### 3. Configuration (`.env`)

```
LLM_PROVIDER=huggingface
HF_MODEL_ID=tencent/Hy-MT2-1.8B
HF_MAX_NEW_TOKENS=512
```

Requires `transformers>=5.6` (included in `requirements.txt`).

**Other HF models** (edit `HF_MODEL_ID`):

| Model | Size | Notes |
|-------|------|--------|
| `tencent/Hy-MT2-1.8B` | ~4 GB | **Default**; Tencent MT, excellent Japanese |
| `tencent/Hy-MT2-7B` | ~14 GB | Higher quality, more VRAM/RAM |
| `Qwen/Qwen2.5-1.5B-Instruct` | ~3 GB | General instruct model |
| `Qwen/Qwen2.5-0.5B-Instruct` | ~1 GB | Fastest; weaker output |

After the first download, works **offline** from the cache.

---

## Option B: LM Studio

If you prefer a GUI to manage models:

```
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL=local-model
```

Start LM Studio → load model → Start Server.

---

## Option C: Ollama

Only if `ollama --version` works (see MLX crash note below).

```
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b
```

---

## Ollama crashes on Windows? (`0xc0000005`)

Known bug — use **Hugging Face** (default) or **LM Studio** instead. See [ollama#15481](https://github.com/ollama/ollama/issues/15481).

---

## Anki import

1. **Download ZIP (TSV + MP3)**
2. Anki → **File → Import** → `anki_import.tsv`
3. Map columns (Expression, Example, ExampleAudio, …)

---

## Troubleshooting

**Slow first run** — Normal; downloading + loading ~4 GB for Hy-MT2-1.8B. Use `python scripts\download_model.py` beforehand.

**Upgrade transformers** — Hy-MT2 needs v5.6+: `pip install "transformers>=5.6.0"`.

**Out of memory** — Switch to `HF_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct` or use LM Studio with a quantized GGUF.

**CUDA** — If you have an NVIDIA GPU, PyTorch will use it automatically for faster inference.

**Invalid JSON from model** — Retry, or use `Qwen2.5-3B-Instruct`.

---

## API

- `GET /api/health` — provider status, cache state
- `POST /api/generate` — card + TSV + audio
- `POST /api/generate/download` — Anki ZIP
