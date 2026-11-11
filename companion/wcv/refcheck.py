"""Checking a reference clip against its text with Whisper: CatQuest's subtitle timings are not
exact, and a clip that holds a word of the next sentence makes F5 say that word before every line
("…нести в сердце горе" from nightelf-female#53). Used once, when the voice bank is built."""
from __future__ import annotations

import difflib
import re

MODEL = "openai/whisper-large-v3-turbo"
GOOD = 0.85          # word similarity at or above which a clip is taken


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower().replace("ё", "е").replace("+", ""))


def similarity(expected: str, heard: str) -> float:
    """How alike the words are (0..1); extra or missing words lower it."""
    return difflib.SequenceMatcher(None, words(expected), words(heard)).ratio()


class Checker:
    def __init__(self, log):
        self.log = log
        self.pipe = None

    def load(self) -> bool:
        try:
            import torch
            from transformers import pipeline
            self.pipe = pipeline("automatic-speech-recognition", model=MODEL, torch_dtype=torch.float16,
                                 device="cuda")
            return True
        except Exception as e:  # noqa: BLE001 - without it the bank is built unchecked, as before
            self.log(f"проверка образцов недоступна ({e}); беру отрезки без проверки")
            return False

    def score(self, samples, rate: int, expected: str) -> tuple[float, str]:
        out = self.pipe({"raw": samples, "sampling_rate": rate},
                        generate_kwargs={"language": "russian", "task": "transcribe"})
        heard = out.get("text", "")
        return similarity(expected, heard), heard
