import pykakasi

_kks = None


def _get() -> pykakasi.kakasi:
    global _kks
    if _kks is None:
        _kks = pykakasi.kakasi()
    return _kks


def word_reading(word: str) -> str:
    kks = _get()
    return "".join(item["hira"] for item in kks.convert(word))


def sentence_reading(sentence: str) -> str:
    kks = _get()
    return "".join(item["hira"] for item in kks.convert(sentence))


def build_furigana(text: str) -> str:
    kks = _get()
    parts: list[str] = []
    for item in kks.convert(text):
        o = item["orig"]
        h = item["hira"]
        if o != h:
            parts.append(f"{o}[{h}]")
        else:
            parts.append(o)
    return "".join(parts)
