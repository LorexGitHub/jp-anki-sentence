"""Pre-download the Hugging Face model (optional — also happens on first generate)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.services.hf_llm import _load_model


def main() -> None:
    print(f"Downloading / loading {settings.hf_model_id} …")
    _load_model()
    print("Done. Model is cached for offline use.")


if __name__ == "__main__":
    main()
