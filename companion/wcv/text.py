"""Text before speech: stress marks (RUAccent, the dictionary's own marks kept), numbers as words,
and stress marks in the form each engine takes."""
from __future__ import annotations

import re
import threading

STRESS = re.compile(r"\+([аеёиоуыэюяАЕЁИОУЫЭЮЯ])")
WORD = re.compile(r"[\w+]+")
CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
NUMBER = re.compile(r"\d+")


def apply_stress(text: str, mode: str) -> str:
    """Stress marks written as "+" before a vowel, as an engine takes them: "plus" keeps them,
    "acute" puts U+0301 after the vowel, "strip" removes them."""
    if mode == "plus":
        return text
    if mode == "acute":
        return STRESS.sub(lambda m: m.group(1) + "́", text)
    return STRESS.sub(r"\1", text)


def merge_marks(original: str, accented: str) -> str:
    """`accented` (RUAccent's output for `original` without its "+") with the words that already
    had a "+" in `original` put back as they were: the dictionary's marks win. When the words do
    not line up one to one, `original` is returned unchanged."""
    words = WORD.findall(original)
    spans = list(WORD.finditer(accented))
    if len(words) != len(spans):
        return original
    out, last = [], 0
    for word, span in zip(words, spans):
        out.append(accented[last:span.start()])
        out.append(word if "+" in word else span.group())
        last = span.end()
    out.append(accented[last:])
    return "".join(out)


NEXT_WORD = re.compile(r"\s+([а-яёА-ЯЁ+]+)")
GENDERS = {"masc", "femn", "neut"}
OBLIQUE = {"gent", "datv", "ablt", "loct"}
_morph = None
_morph_lock = threading.Lock()


def _analyzer():
    """pymorphy3's analyzer, loaded once (None without pymorphy3)."""
    global _morph
    with _morph_lock:
        if _morph is None:
            try:
                import pymorphy3
                _morph = pymorphy3.MorphAnalyzer()
            except ImportError:
                _morph = False
    return _morph or None


def agree(n: int, spoken: str, following: str, morph) -> str:
    """`spoken` (num2words' nominative for `n`) agreeing with the word after it:
    "1 руку" -> "одну", "без 1 руки" -> "одной", "2 руки" -> "две", "с 5 магами" -> "пятью".
    Left as it is when the word is not a noun or adjective, not in pymorphy's dictionary (slang:
    "2 дамагера"), or could be the plain nominative ("1 золотой")."""
    word = following.replace("+", "").lower()
    if not morph.word_is_known(word):
        return spoken                                  # a guess ("дамагера" as feminine) does worse
    parses = [p for p in morph.parse(word) if p.tag.POS in ("NOUN", "ADJF", "PRTF")]
    if not parses:
        return spoken
    parts = spoken.split()

    def to_case(words, case):
        out = []
        for w in words:
            form = morph.parse(w)[0].inflect({case})
            out.append(form.word if form else w)
        return out

    teen = 10 < n % 100 < 20
    if n % 10 == 1 and not teen:
        sing = [p for p in parses if p.tag.number == "sing"]
        if not sing or any(p.tag.case == "nomn" and p.tag.gender in ("masc", None) for p in sing):
            return spoken
        tag = sing[0].tag
        tags = {tag.case} | ({tag.gender} if tag.gender in GENDERS else set())
        if tag.case == "accs" and tag.gender == "masc" and tag.animacy:
            tags.add(tag.animacy)                      # "на 1 мага" - "одного"
        one = morph.parse("один")[0].inflect(tags)
        if one:
            parts[-1] = one.word
        if tag.case in OBLIQUE:                        # "с 21 магом" - "двадцатью одним"
            parts[:-1] = to_case(parts[:-1], tag.case)
        return " ".join(parts)
    tag = parses[0].tag
    if tag.number == "plur" and tag.case in ("datv", "ablt", "loct"):
        return " ".join(to_case(parts, tag.case))       # "в 3 сумках" - "трёх"
    if n % 10 == 2 and not teen and parts[-1] == "два" and tag.gender == "femn":
        parts[-1] = "две"                              # "2 руки" - "две"
    return " ".join(parts)


def numbers_to_words(text: str) -> str:
    """Digits as Russian words, agreeing with the word after them where pymorphy3 can tell how."""
    try:
        from num2words import num2words
    except ImportError:
        return text
    morph = _analyzer()

    def spell(m):
        if len(m.group()) >= 10:
            return m.group()
        n = int(m.group())
        spoken = num2words(n, lang="ru")
        following = NEXT_WORD.match(m.string, m.end())
        if morph is not None and following:
            try:
                spoken = agree(n, spoken, following.group(1), morph)
            except Exception:  # noqa: BLE001 - a number read in the nominative is still a number
                pass
        return spoken

    return NUMBER.sub(spell, text)


class Accentor:
    """RUAccent, loaded on first use (about 10 s; the models are cached by Hugging Face)."""

    def __init__(self, log, enabled: bool = True):
        self.log, self.enabled, self.model = log, enabled, None
        self.lock = threading.Lock()   # shared by the engines' threads

    def load(self) -> None:
        with self.lock:
            self._load()

    def _load(self) -> None:
        if not self.enabled or self.model is not None:
            return
        try:
            import numpy as np
            from ruaccent import RUAccent
        except ImportError:
            self.log("RUAccent не установлен: ударения только из словаря")
            self.enabled = False
            return
        model = RUAccent()
        model.load(omograph_model_size="turbo3.1", use_dictionary=True, tiny_mode=False)
        # This ruaccent does not feed token_type_ids, which its downloaded ONNX models want: zeros.
        for part in vars(model).values():
            session = getattr(part, "session", None)
            if session is None or "token_type_ids" not in {i.name for i in session.get_inputs()}:
                continue

            def run(outputs, feed, *a, _run=session.run, **k):
                if "token_type_ids" not in feed and "input_ids" in feed:
                    feed = dict(feed)
                    feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
                return _run(outputs, feed, *a, **k)

            session.run = run
        self.model = model

    def accent(self, text: str) -> str:
        """`text` with "+" before each stressed vowel; words marked by the dictionary kept."""
        if not self.enabled or not CYRILLIC.search(text):
            return text
        self.load()
        if self.model is None:
            return text
        try:
            with self.lock:
                accented = self.model.process_all(text.replace("+", ""))
        except Exception as e:  # noqa: BLE001 - never lose a line over stress marks
            self.log(f"RUAccent: {e}")
            return text
        return merge_marks(text, accented)
