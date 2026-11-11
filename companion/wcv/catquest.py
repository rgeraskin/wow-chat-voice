"""The voice bank for F5-TTS: reference clips cut from the user's own CatQuest_Voices pack.

Nothing of CatQuest is shipped: on first run the clips are cut from the installed pack. Each voice
id of the pack ("orc-male", "orc-male#60", "creature/saurfang", ...) gets one reference clip of
whole sentences (5..12 s) with its exact text, and each race voice also gets copies shifted in
pitch, so characters of one race and sex can sound apart.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

BANK_VERSION = 5
SAMPLE_RATE = 24000
RACE_VOICE = re.compile(r"^([a-z]+)-(male|female)(#\d+)?$")
# Russian questions with a question word ("Кто идёт?") fall in pitch; a yes/no question ("Ты
# поможешь нам?") rises - the intonation a question reference is for.
QUESTION_WORDS = {"кто", "что", "чего", "чему", "чем", "кого", "кому", "кем", "где", "куда", "откуда", "когда",
                  "как", "почему", "зачем", "отчего", "сколько", "какой", "какая", "какое", "какие", "каков",
                  "какова", "чей", "чья", "чьё", "чье", "чьи", "разве", "неужели", "ну", "а", "и", "так"}


def question_score(sentences: list[str]) -> float:
    """How good a run of sentences is as a reference for a rising question; 0: unfit. The last
    sentence must be a yes/no question; any "!" (an indignant, rhetorical tone) rules it out."""
    if not sentences or not sentences[-1].rstrip().endswith("?"):
        return 0.0
    if any("!" in s for s in sentences):
        return 0.0
    first = re.findall(r"[а-яё]+", sentences[-1].lower())
    if not first or first[0] in QUESTION_WORDS:
        return 0.0
    score = 1.0
    if all(s.rstrip().endswith("?") for s in sentences):
        score += 1.0                                 # questions only: no statement prosody in it
    if re.search(r"\bли\b", sentences[-1].lower()):
        score += 0.5                                 # "Готов ли ты?" - plainly a yes/no question
    return score
SKIP_RACES = {"child", "succubus"}


@dataclass(frozen=True)
class Slot:
    """One voice a character can be given: a reference clip and its text."""
    id: str          # "orc-male#60", "orc-male#60^-1.5" for a pitch-shifted copy
    base: str        # the pack's voice id
    race: str        # "orc", "" for creatures and named voices
    sex: str         # "male", "female", ""
    shift: float     # semitones
    path: str
    text: str
    q_path: str = ""   # a clip ending in a question, for lines that end in "?" (F5 copies intonation)
    q_text: str = ""


def find_pack(config: dict) -> Path | None:
    """CatQuest_Voices: the configured folder, else the usual WoW install places."""
    if config.get("catquest_dir"):
        path = Path(config["catquest_dir"])
        return path if (path / "Index.lua").exists() else None
    for drive in "CDEFGH":
        for root in (f"{drive}:/World of Warcraft", f"{drive}:/Games/World of Warcraft",
                     f"{drive}:/Program Files (x86)/World of Warcraft", f"{drive}:/Program Files/World of Warcraft"):
            for flavor in ("_forever_", "_retail_"):
                path = Path(root) / flavor / "Interface/AddOns/CatQuest_Voices"
                if (path / "Index.lua").exists():
                    return path
    return None


def _quests(index_lua: Path) -> dict:
    """CatQuestVoicePack.quests as Python data (Lua 5.4 through lupa: the file has too many
    constants for LuaJIT)."""
    from lupa import lua54

    lua = lua54.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(index_lua.read_text(encoding="utf-8"))
    quests = lua.globals().CatQuestVoicePack.quests

    def py(value):
        if lua54.lua_type(value) == "table":
            keys = list(value.keys())
            if keys and all(isinstance(k, int) for k in keys):
                return [py(value[k]) for k in sorted(keys)]
            return {k: py(value[k]) for k in keys}
        return value

    return {int(k): py(v) for k, v in quests.items()}


def _candidates(quests: dict) -> dict[str, list[dict]]:
    """Per voice id: runs of whole sentences 5..12 s long, best (nearest 8 s) first."""
    found: dict[str, list[dict]] = {}

    def add(voice, file, duration, subs):
        if not (voice and subs):
            return
        for i in range(len(subs)):
            for j in range(i, len(subs)):
                start = subs[i][0]
                end = subs[j + 1][0] if j + 1 < len(subs) else duration
                length = end - start
                if length > 12:
                    break
                sentences = [s[1] for s in subs[i:j + 1]]
                text = " ".join(sentences)
                if re.search(r"[\d%]", text):
                    continue
                if length >= 5:
                    found.setdefault(voice, []).append(
                        {"file": file, "start": start, "end": end, "text": text, "score": abs(length - 8),
                         "question": False})
                q = question_score(sentences) if 4 <= length <= 10 else 0.0
                if q:
                    # best first: the higher question score, then nearer 6 s
                    found.setdefault(voice, []).append(
                        {"file": file, "start": start, "end": end, "text": text,
                         "score": -q * 10 + abs(length - 6), "question": True})

    def entry(qid, suffix, data, voice):
        for key, subs in (data.get("c") or {}).items():
            name = f"{qid}{suffix}" if key == "x" else f"{qid}{suffix}_{key}"
            add(data.get("v") or voice, f"{name}.ogg", data.get("d"), subs)

    for qid, quest in quests.items():
        entry(qid, "", quest, quest.get("v"))
        if quest.get("t"):
            entry(qid, "_t", quest["t"], quest.get("v"))
    for voice in found:
        found[voice].sort(key=lambda c: c["score"])
    return found


def _shift(samples, semitones: float):
    """Pitch shift by resampling: a little higher (or lower) and a little faster (or slower) -
    for a reference clip that is only a different, still natural voice."""
    import numpy as np

    factor = 2 ** (semitones / 12)
    n = int(len(samples) / factor)
    return np.interp(np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples).astype("float32")


def build(pack: Path, out: Path, shifts: list[float], log, make_checker=None) -> list[Slot]:
    """Cut the reference clips into `out` (once; kept while the pack and settings are the same).
    With `make_checker` (returns a refcheck.Checker, or None), each clip is heard by Whisper and one
    whose words do not match its subtitles is passed over for the voice's next best clip; Whisper is
    loaded only when the bank is actually (re)built. A checked bank is never rebuilt unchecked."""
    stamp = {"version": BANK_VERSION, "pack": str(pack), "index_size": (pack / "Index.lua").stat().st_size,
             "shifts": shifts}
    manifest = out / "bank.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        old = dict(saved.get("stamp", {}))
        checked = old.pop("checked", False)
        if old == stamp and (checked or make_checker is None):
            return [Slot(**s) for s in saved["slots"]]
    import numpy as np
    import soundfile as sf

    checker = make_checker() if make_checker else None
    stamp["checked"] = checker is not None

    log(f"готовлю голоса из {pack}" + (" (с проверкой образцов, несколько минут)" if checker else "") + " ...")
    rejected = 0
    out.mkdir(parents=True, exist_ok=True)
    candidates = _candidates(_quests(pack / "Index.lua"))
    slots: list[Slot] = []
    for voice, options in sorted(candidates.items()):
        match = RACE_VOICE.match(voice)
        race, sex = (match.group(1), match.group(2)) if match else ("", "")
        if race in SKIP_RACES:
            continue
        def cut(c):
            data, sr = sf.read(str(pack / "Sounds" / "q" / c["file"]), dtype="float32", always_2d=True)
            mono = data.mean(axis=1)[int(c["start"] * sr):int(c["end"] * sr)]
            if sr != SAMPLE_RATE:
                mono = np.interp(np.linspace(0, len(mono) - 1, int(len(mono) * SAMPLE_RATE / sr)),
                                 np.arange(len(mono)), mono).astype("float32")
            return mono

        def first(wanted):
            """The first clip that exists - and, with a checker, that Whisper hears as its text
            (else the one heard closest)."""
            nonlocal rejected
            best, best_score = None, -1.0
            for option in wanted[:6]:
                if not (pack / "Sounds" / "q" / option["file"]).exists():
                    continue
                if checker is None:
                    return option, cut(option)
                audio = cut(option)
                score, heard = checker.score(audio, SAMPLE_RATE, option["text"])
                if score >= 0.85:
                    return option, audio
                rejected += 1
                if score > best_score:
                    best, best_score = (option, audio), score
            return best if best else (None, None)

        clip, mono = first([o for o in options if not o["question"]] or options)
        if clip is None:
            continue
        qclip, qmono = first([o for o in options if o["question"]])
        safe = voice.replace("/", "_").replace("#", "_")
        for shift in ([0.0] + list(shifts)) if race else [0.0]:
            slot_id = voice if shift == 0 else f"{voice}^{shift:+g}"
            suffix = "" if shift == 0 else f"_{shift:+g}"
            path = out / f"{safe}{suffix}.wav"
            sf.write(str(path), mono if shift == 0 else _shift(mono, shift), SAMPLE_RATE)
            q_path = ""
            if qmono is not None:
                q_path = str(out / f"{safe}{suffix}_q.wav")
                sf.write(q_path, qmono if shift == 0 else _shift(qmono, shift), SAMPLE_RATE)
            slots.append(Slot(slot_id, voice, race, sex, shift, str(path), clip["text"], q_path,
                              qclip["text"] if qclip else ""))
    manifest.write_text(json.dumps({"stamp": stamp, "slots": [s.__dict__ for s in slots]},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"голосов: {len({s.base for s in slots})}, вариантов с тембром: {len(slots)}, "
        f"с образцом вопроса: {len({s.base for s in slots if s.q_path})}"
        + (f"; отрезков отбраковано проверкой: {rejected}" if checker else ""))
    return slots
