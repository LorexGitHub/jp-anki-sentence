import logging

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

logger = logging.getLogger(__name__)

MODEL_ID = "Helsinki-NLP/opus-mt-ja-en"

_model = None
_tokenizer = None


def _load():
    global _model, _tokenizer
    if _model is None:
        logger.info("Loading translation model %s …", MODEL_ID)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID).to(device)
        _model.eval()
        logger.info("Translation model loaded on %s.", device)
    return _model, _tokenizer


def translate(japanese_text: str) -> str:
    model, tokenizer = _load()
    inputs = tokenizer(
        japanese_text,
        return_tensors="pt",
        padding=True,
        truncation=True,
    )
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.inference_mode():
        output_ids = model.generate(**inputs, max_new_tokens=128)

    result = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    return result.strip()
