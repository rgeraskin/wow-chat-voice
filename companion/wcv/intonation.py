"""Question intonation on top of F5 (Praat PSOLA through parselmouth: the pitch and the timing change,
the voice does not).

F5 says "Идёшь с нами?" as often as not like a statement, and question references did not help (the
CatQuest voices are F5 output themselves). So:
- a yes/no question ("Идёшь с нами?") gets its end lifted: the last `span` seconds of voice rise to
  `yes_no_rise_st` semitones above the line's median pitch. F5 also lets the last syllable of a line
  die away like a statement's ("Есть хил в гр+уппу?": "-пу", after the "пп" pause, is 15-20 dB below
  the rest), so the rise lands on something barely heard; that syllable is brought up to
  `yes_no_end_db` dB below the loud parts of the line (None turns this off);
- a question with a question word ("Кто идёт?") falls in Russian; it gets a peak of `wh_peak_st`
  semitones on the stressed vowel of the question word instead.

The question word's place in time is estimated from where its stressed vowel sits among the vowels of
the line (syllables take roughly even time): no recogniser is needed.
"""
from __future__ import annotations

import re

QUESTION_WORDS = {"кто", "что", "чего", "чему", "чем", "кого", "кому", "кем", "где", "куда", "откуда", "когда",
                  "как", "почему", "зачем", "отчего", "сколько", "какой", "какая", "какое", "какие", "каков",
                  "какова", "чей", "чья", "чьё", "чье", "чьи", "каким", "какую", "какого", "скольких"}
LEADING = {"а", "и", "но", "ну", "так", "ой", "эй", "слушай", "слушайте"}   # skipped before the question word
VOWELS = "аеёиоуыэюя"
WORD = re.compile(r"[а-яё+]+(?:-[а-яё+]+)*")   # "кто-нибудь" is one word, and not a question word

DEFAULTS = {"yes_no_rise_st": 7, "yes_no_end_db": 8, "wh_peak_st": 6}
# The estimate of the stressed vowel is off by ~0.12 s on average (checked against Whisper word
# times), so the peak is wide enough to lift the whole question word.
WH_WIDTH = 0.16


def _last_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?…])\s+", text.strip())[-1]


def question_word(text: str) -> int | None:
    """Index (among the words of `text`, "+" kept in them) of the question word that opens the last
    sentence when it is a question: "Ну кто идёт?" -> 1. None for statements and yes/no questions."""
    text = text.lower()
    if not text.rstrip().endswith("?"):
        return None
    words = WORD.findall(text)
    last = WORD.findall(_last_sentence(text))
    i = len(words) - len(last)
    while i < len(words) and words[i].replace("+", "") in LEADING:
        i += 1
    return i if i < len(words) and words[i].replace("+", "") in QUESTION_WORDS else None


def is_yes_no(text: str) -> bool:
    """The last sentence of `text` asks yes or no: ends in "?" with no question word up front."""
    last = _last_sentence(text.replace("+", "").lower())
    return last.endswith("?") and bool(WORD.findall(last)) and question_word(text) is None


def kind(text: str) -> str | None:
    if question_word(text) is not None:
        return "wh"
    return "yes_no" if is_yes_no(text) else None


def stressed_vowel(text: str, word_index: int) -> tuple[int, int]:
    """(index of the stressed vowel of word `word_index` among all vowels of `text`, vowel count).
    The stress is RUAccent's "+" (before the vowel), else "ё", else the first vowel."""
    words = WORD.findall(text.lower())
    before = sum(sum(ch in VOWELS for ch in w) for w in words[:word_index])
    w = words[word_index]
    if "+" in w:
        k = sum(ch in VOWELS for ch in w[: w.index("+")])
    elif "ё" in w:
        k = sum(ch in VOWELS for ch in w[: w.index("ё")])
    else:
        k = 0
    return before + k, max(1, sum(sum(ch in VOWELS for ch in w) for w in words))


def speech_span(samples, rate: int) -> tuple[float, float]:
    """Start and end of the voice (20 ms frames louder than a tenth of the loudest)."""
    import numpy as np
    frame = int(rate * 0.02)
    x = np.asarray(samples, dtype="float32")
    n = len(x) // frame
    if n == 0:
        return 0.0, len(x) / rate
    rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1))
    on = np.where(rms > 0.1 * rms.max())[0]
    return on[0] * frame / rate, (on[-1] + 1) * frame / rate


def _ease(a: float, b: float, x: float) -> float:
    import numpy as np
    x = min(1.0, max(0.0, x))
    return a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * x))


def shape(samples, rate: int, text: str, settings: dict | None = None):
    """`samples` (the voice of `text`) with question intonation, or unchanged when `text` is not a
    question, the setting for its kind is 0, parselmouth is missing or there is too little voice."""
    settings = {**DEFAULTS, **(settings or {})}
    what = kind(text)
    if what is None or not settings["yes_no_rise_st" if what == "yes_no" else "wh_peak_st"]:
        return samples
    try:
        import numpy as np
        import parselmouth
        from parselmouth.praat import call
    except ImportError:
        return samples
    snd = parselmouth.Sound(np.asarray(samples, dtype="float64"), sampling_frequency=rate)
    manip = call(snd, "To Manipulation", 0.01, 60, 500)
    tier = call(manip, "Extract pitch tier")
    n = call(tier, "Get number of points")
    if n < 5:
        return samples
    pts = [(call(tier, "Get time from index", i), call(tier, "Get value at index", i)) for i in range(1, n + 1)]
    median = float(np.median([f for _, f in pts]))
    new = call("Create PitchTier", "question", snd.xmin, snd.xmax)

    if what == "yes_no":
        span = 0.45
        end = pts[-1][0]
        start = end - span
        target = median * 2 ** (settings["yes_no_rise_st"] / 12)
        f_start = float(np.interp(start, [p[0] for p in pts], [p[1] for p in pts]))
        for t, f in pts:
            if t < start:
                call(new, "Add point", t, f)
        for k in range(21):
            call(new, "Add point", start + span * k / 20, _ease(f_start, target, k / 20))
    else:
        a, b = speech_span(samples, rate)
        k, count = stressed_vowel(text, question_word(text))
        centre = a + (k + 0.5) / count * (b - a)
        for t, f in pts:
            call(new, "Add point", t, f * 2 ** (settings["wh_peak_st"] * np.exp(-((t - centre) / WH_WIDTH) ** 2) / 12))

    call([new, manip], "Replace pitch tier")
    out = call(manip, "Get resynthesis (overlap-add)").values[0].astype("float32")
    if what == "yes_no" and settings["yes_no_end_db"] is not None:
        out = boost_last_syllable(out, rate, settings["yes_no_end_db"])
    return out


def boost_last_syllable(samples, rate: int, below_db: float = 4.0, max_gain_db: float = 18.0):
    """The last run of sound (after the last gap of 40 ms or more) raised so its peak is `below_db`
    under the loud parts of the line (the 90th percentile of the 10 ms levels); unchanged when it is
    already that loud. The gain fades in and out over 15 ms, inside the gaps, so there are no clicks."""
    import numpy as np
    x = np.asarray(samples, dtype="float32")
    n = int(rate * 0.01)
    k = len(x) // n
    if k < 10:
        return x
    db = 20 * np.log10(np.sqrt(np.mean(x[: k * n].reshape(k, n) ** 2, axis=1)) + 1e-9)
    floor = db.max() - 40
    sound = db > floor
    frames = np.where(sound)[0]
    if len(frames) == 0:
        return x
    end = frames[-1]
    start = end
    while start > 0 and (sound[start - 1] or (sound[max(0, start - 4):start].any())):
        start -= 1                      # walk back over the run, bridging gaps under 40 ms
    if start <= frames[0]:
        return x                        # one run: nothing died away at the end
    loud = np.percentile(db[frames[0]:start][sound[frames[0]:start]], 90)
    gain_db = min(max_gain_db, loud - below_db - db[start:end + 1].max())
    if gain_db <= 0.5:
        return x
    gain = np.ones(len(x), dtype="float32")
    a, b = start * n, min(len(x), (end + 1) * n + int(0.03 * rate))
    fade = int(0.015 * rate)
    g = 10 ** (gain_db / 20)
    gain[a:b] = g
    gain[max(0, a - fade):a] = np.linspace(1, g, a - max(0, a - fade))
    gain[b:b + fade] = np.linspace(g, 1, len(gain[b:b + fade]))
    y = x * gain
    peak = float(np.abs(y).max())
    return y / peak * 0.95 if peak > 0.95 else y
