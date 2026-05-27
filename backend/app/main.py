import base64
import logging
import threading
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.config import settings
from app.models import CardPayload, GenerateRequest, GenerateResponse, AddToAnkiRequest, AddToAnkiResponse, TaskControlRequest, AddBatchRequest
from app.services.anki_export import IMPORT_NOTES
from app.services.ankiconnect import add_card as ankiconnect_add, add_cards_batch as ankiconnect_add_batch, ping as ankiconnect_ping
from app.services.apkg_service import process_apkg
from app.services.llm import LLMError, check_llm_status
from app.services.pipeline import build_card_bundle
from app.services.tts import zip_download_filename

logger = logging.getLogger(__name__)

_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


def _preload_model_background() -> None:
    if settings.llm_provider != "huggingface" or not settings.hf_preload_on_startup:
        return

    def _run() -> None:
        try:
            from app.services.hf_llm import _load_model

            logger.info("Preloading model %s …", settings.hf_model_id)
            _load_model()
            logger.info("Model preloaded and ready.")
        except Exception as exc:
            logger.warning("Model preload failed: %s", exc)

    threading.Thread(target=_run, daemon=True, name="hf-preload").start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _preload_model_background()
    yield


app = FastAPI(title="JP Anki Sentence Generator", version="1.0.0", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    llm = check_llm_status()
    is_hf = llm["provider"] == "huggingface"
    ready = llm["server_running"] and (
        is_hf or llm["model_available"] or not llm["available_models"]
    )
    return {
        "ok": ready,
        "llm_provider": llm["provider"],
        "base_url": llm["base_url"],
        "model": llm["model"],
        "server_running": llm["server_running"],
        "model_available": llm["model_available"],
        "model_cached": llm.get("model_cached"),
        "model_loading": llm.get("model_loading"),
        "model_loaded_in_memory": llm.get("model_loaded_in_memory"),
        "available_models": llm["available_models"],
        "setup_hint": llm["setup_hint"],
        "preload_on_startup": settings.hf_preload_on_startup,
        "ollama_mlx_crash_note": llm.get("ollama_mlx_crash_note"),
        "tts_voice": settings.tts_voice,
        "anki_deck_name": settings.anki_deck_name,
        "anki_model_name": settings.anki_model_name,
    }


def _bundle_or_http_error(word: str, *, use_cache: bool = True):
    try:
        return build_card_bundle(word, use_cache=use_cache)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Generation failed: {exc}") from exc


@app.post("/api/generate", response_model=GenerateResponse)
def generate_json(body: GenerateRequest):
    word = body.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word is required.")

    bundle = _bundle_or_http_error(word, use_cache=True)
    audio_b64 = base64.b64encode(bundle.audio_bytes).decode("ascii")

    return GenerateResponse(
        card=bundle.card,
        anki_tsv=bundle.tsv,
        import_notes=IMPORT_NOTES,
        sentence_audio_base64=audio_b64,
    )


@app.post("/api/generate/download")
def generate_download(body: GenerateRequest):
    word = body.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word is required.")

    bundle = _bundle_or_http_error(word, use_cache=True)
    filename = zip_download_filename(word)

    return Response(
        content=bundle.zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.post("/api/add-to-anki", response_model=AddToAnkiResponse)
def add_to_anki(body: AddToAnkiRequest):
    word = body.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word is required.")

    bundle = _bundle_or_http_error(word, use_cache=True)
    try:
        note_id = ankiconnect_add(bundle.card, bundle.audio_bytes)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AnkiConnect failed: {exc}")

    return AddToAnkiResponse(success=True, note_id=note_id)


@app.post("/api/add-to-anki/batch")
def add_to_anki_batch(body: AddBatchRequest):
    if not body.words:
        raise HTTPException(status_code=400, detail="No words provided")

    cards: list[tuple[CardPayload, bytes]] = []
    errors: list[str] = []
    for word in body.words:
        w = word.strip()
        if not w:
            continue
        try:
            bundle = _bundle_or_http_error(w, use_cache=True)
            cards.append((bundle.card, bundle.audio_bytes))
        except Exception as exc:
            errors.append(f"{w}: {exc}")

    if not cards:
        raise HTTPException(status_code=502, detail=f"All words failed: {'; '.join(errors[:5])}")

    try:
        result = ankiconnect_add_batch(cards)
        result["errors"] = errors
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AnkiConnect failed: {exc}")


@app.post("/api/upload-apkg")
async def upload_apkg(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".apkg"):
        raise HTTPException(status_code=400, detail="File must be a .apkg file")

    file_bytes = await file.read()
    task_id = uuid.uuid4().hex[:12]

    progress: dict = {}
    control: dict = {"paused": False, "skip_to": None}
    with _tasks_lock:
        _tasks[task_id] = {"status": "processing", "progress": progress, "control": control}

    def _run() -> None:
        try:
            result_bytes = process_apkg(file_bytes, progress=progress, control=control)
            with _tasks_lock:
                _tasks[task_id].update({"status": "done", "result": result_bytes})
        except Exception as exc:
            logger.exception("APKG processing failed")
            with _tasks_lock:
                _tasks[task_id].update({"status": "error", "error": str(exc)})

    threading.Thread(target=_run, daemon=True, name=f"apkg-{task_id}").start()
    return {"task_id": task_id}


@app.get("/api/task/{task_id}")
def task_status(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    resp: dict[str, object] = {
        "status": task["status"],
        "error": task.get("error"),
    }

    ctrl = task.get("control")
    if ctrl is not None:
        resp["paused"] = ctrl.get("paused", False)

    p = task.get("progress")
    if p is not None:
        resp["words"] = p.get("words", [])
        resp["current_index"] = p.get("current_index", -1)
        resp["completed_words"] = list(p.get("results", {}).keys())
        resp["failed_words"] = {w: p["errors"][w] for w in p.get("errors", {})}

    return resp


@app.get("/api/task/{task_id}/preview/{word:path}")
def task_preview_word(task_id: str, word: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    p = task.get("progress")
    if not p:
        raise HTTPException(status_code=400, detail="No progress data available")

    result = p.get("results", {}).get(word)
    if not result:
        raise HTTPException(status_code=404, detail="Word not yet processed")

    audio_b64 = base64.b64encode(result["audio_bytes"]).decode("ascii")
    return GenerateResponse(
        card=CardPayload(**result["card"]),
        anki_tsv=result["tsv"],
        import_notes=IMPORT_NOTES,
        sentence_audio_base64=audio_b64,
    )


@app.get("/api/task/{task_id}/download")
def task_download(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "done":
        raise HTTPException(status_code=400, detail="Task not yet complete")
    result = task.get("result")
    if not result:
        raise HTTPException(status_code=500, detail="No result data")
    return Response(
        content=result,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="jp_sentences.apkg"',
        },
    )


@app.post("/api/task/{task_id}/control")
def control_task(task_id: str, body: TaskControlRequest):
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        ctrl = task.get("control")
        if ctrl is None:
            raise HTTPException(status_code=400, detail="Task has no control interface")

        if body.action == "pause":
            ctrl["paused"] = True
            task["status"] = "paused"
        elif body.action == "resume":
            ctrl["paused"] = False
            task["status"] = "processing"
        elif body.action == "skip":
            if body.index is None:
                raise HTTPException(status_code=400, detail="index required for skip action")
            ctrl["skip_to"] = body.index
            ctrl["paused"] = False
            task["status"] = "processing"
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

    return {"ok": True}
