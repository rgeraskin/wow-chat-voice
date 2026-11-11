"""WoW Chat Voice companion: reads the addon's strip off the WoW window and speaks each chat line.

Run: python -m wcv  (config.json next to the wcv folder is created on first run)
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from . import protocol

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_CONFIG = {
    "_help": "rate -10..10, volume 0..100. exclude: voices left out (part of the name). "
             "gender_overrides: voices whose gender SAPI does not know. players: {\"Name\": \"part of a voice name\"}. "
             "stress: how each engine gets the dictionary's stress marks (plus, acute or strip). "
             "engine: f5 (CatQuest race voices on an NVIDIA GPU) or sapi (Windows voices). "
             "voice_shifts: semitones of the extra copies of each race voice. players: also takes F5 voice ids (orc-male#60).",
    "engine": "f5",
    "rate": 0,
    "volume": 100,
    "max_queue": 8,
    "exclude": ["Irina Desktop", "Dmitry Online"],
    "gender_overrides": {"Aidar": "Male", "Eugene": "Male", "Baya": "Female", "Kseniya": "Female", "Xenia": "Female"},
    "players": {},
    "stress": {"rhvoice": "acute", "silero": "plus", "edge": "strip", "other": "strip"},
    "ruaccent": True,
    "declension": True,
    "nfe_step": 16,
    "f5_margin": 1.25,
    "f5_tail": 0.5,
    "f5_question_refs": False,
    # F5 only; 0 turns a part off. See wcv/intonation.py.
    "question_intonation": {"yes_no_rise_st": 7, "yes_no_end_db": 8, "wh_peak_st": 6},
    "check_refs": True,
    "kind_gain_db": {"yell": 3, "whisper": -4},
    "voice_shifts": [-1.5, 1.5],
    "catquest_dir": "",
    "wow_dir": "",
    "hf_home": "",
    "launch_wow": True,
    "launch_product": "WoWF",
    "battlenet_exe": "",
    "exit_with_wow": True,
    "spoken_notices": False,
    "log_details": True,
    "log_keep_days": 90,
    "debug": False,
    "poll_interval": 0.05,
    "capture_height": 16,
    "window_capture": True,
}
MARKUP = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|T.*?\|t|\|A.*?\|a")
LABELS = {"party": "группа", "raid": "рейд", "warning": "объявление", "instance": "подземелье",
          "say": "сказать", "yell": "крик", "whisper": "шёпот", "guild": "гильдия", "officer": "офицеры",
          "channels": "канал", "emote": "эмоция", "test": "тест",
          "notice": "программа"}


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_log_file = None
_log_day = None


def log(message: str) -> None:
    """To the console and to logs/wcv-YYYY-MM-DD.log (appended: one file a day, kept for later)."""
    global _log_file, _log_day
    now = datetime.now()
    line = f"{now:%H:%M:%S} {message}"
    print(line, flush=True)
    try:
        day = f"{now:%Y-%m-%d}"
        if day != _log_day:
            if _log_file is not None:
                _log_file.close()
            LOG_DIR.mkdir(exist_ok=True)
            _log_file = open(LOG_DIR / f"wcv-{day}.log", "a", encoding="utf-8", buffering=1)
            _log_day = day
        _log_file.write(line + "\n")
    except OSError:
        pass


def prune_logs(keep_days: int) -> None:
    """Delete daily logs older than `keep_days` (0: keep them all)."""
    if keep_days <= 0 or not LOG_DIR.is_dir():
        return
    cutoff = datetime.now().timestamp() - keep_days * 86400
    for path in LOG_DIR.glob("wcv-*.log"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config.update(saved)
        if any(key not in saved for key in DEFAULT_CONFIG):   # new settings: write them in
            CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


MODELS_READY = APP_DIR / ".models_ready"


def install_crash_logging() -> None:
    """Uncaught errors - in the main thread or any other - go to the log too, not only the console."""
    import threading
    import traceback

    def report(kind, exc_type, exc, tb):
        log(f"ОШИБКА ({kind}): {exc_type.__name__}: {exc}")
        for chunk in traceback.format_exception(exc_type, exc, tb):
            for line in chunk.rstrip().splitlines():
                log("  " + line)

    sys.excepthook = lambda t, e, tb: report("программа", t, e, tb)
    threading.excepthook = lambda a: report(f"поток {a.thread.name if a.thread else '?'}", a.exc_type,
                                            a.exc_value, a.exc_traceback)


def offline_models() -> bool:
    """After the models were loaded once (F5, Vocos, RUAccent in the Hugging Face cache), never ask
    the hub again: no update checks at start, no "unauthenticated requests" warnings, and nothing
    breaks if the site is down or a model is taken away. Must run before huggingface_hub loads."""
    if MODELS_READY.exists():
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        return True
    return False


def restart_online(log) -> None:
    """A model missing from the cache in offline mode: forget the mark and start again online."""
    MODELS_READY.unlink(missing_ok=True)
    log("в кэше моделей чего-то не хватает — перезапускаюсь с доступом к сети")
    os.execv(sys.executable, [sys.executable, "-m", "wcv"] + sys.argv[1:])


def main() -> int:
    if sys.platform != "win32":
        print("Windows only")
        return 1
    offline = offline_models()
    install_crash_logging()
    from .speech import Speaker
    from .capture import Capturer
    from .window import make_dpi_aware

    make_dpi_aware()

    config = load_config()
    if "--selftest" in sys.argv:
        from .speech import selftest
        selftest(config, log)
        return 0
    if "--selftest-f5" in sys.argv:
        from .f5engine import selftest as f5_selftest
        return f5_selftest(config, log, APP_DIR)
    log("=" * 60)
    log(f"запуск; настройки: {CONFIG_PATH}")
    prune_logs(config["log_keep_days"])
    from . import launch
    if config["launch_wow"] and not launch.wow_running():
        launch.launch(config, log)   # the game starts while the voices load
    from .dictionary import Regexes
    regexes = Regexes(config, log)
    regexes.refresh()
    regexes_checked = time.monotonic()
    from .text import Accentor
    accentor = Accentor(log, config.get("ruaccent", True))
    log("загружаю RUAccent ..." + (" (модели из кэша, без сети)" if offline else ""))
    try:
        accentor.load()
    except Exception as e:  # noqa: BLE001 - offline with a model missing: go online once
        if offline:
            log(f"RUAccent: {e}")
            restart_online(log)
        raise
    from .morph import Inflector, strip_marks
    inflector = Inflector(log, config.get("declension", True))
    inflector.load()
    from .audio import Player
    player = Player(config["max_queue"], APP_DIR / "tmp")
    player.start()
    sapi = Speaker(config, log, accentor, player)
    sapi.start()
    sapi.ready.wait(120)
    log(f"голосов Windows: {len(sapi.all_voices)} (включено {len(sapi.voices)})")
    from . import voicelist
    voicelist.write(config, sapi.all_voices, sapi.default_off, log)
    from .engines import Engines
    engines = Engines(config, log, APP_DIR, sapi, accentor, player)
    engines.on_ready = lambda: MODELS_READY.touch()
    engines.on_error = (lambda error: restart_online(log)) if offline else None
    if "--f5" in sys.argv:
        engines.want("f5")

    seen = None
    linked = False
    window, window_checked = None, 0.0
    first_check = True
    misses = 0
    damaged_since = None      # a strip in view whose frames do not check out, since when
    damaged_told = False
    wow_seen, wow_gone_since, wow_checked = False, None, 0.0
    unknown_kinds: set[str] = set()
    capturer = Capturer(config, log)
    with contextlib.nullcontext():
        while True:
            now = time.monotonic()
            if now - regexes_checked > 5:
                regexes.refresh()
                regexes_checked = now
            if config["exit_with_wow"] and now - wow_checked > 2:
                wow_checked = now
                if launch.wow_running():
                    wow_seen, wow_gone_since = True, None
                elif wow_seen:
                    wow_gone_since = wow_gone_since or now
                    if now - wow_gone_since > 10:
                        log("игра закрыта — выхожу")
                        return 0
            if window is None or now - window_checked > 2:
                found = capturer.find()
                if found != window or first_check:
                    log(f"окно WoW: {found[1]}" if found else "окно WoW не найдено (или свёрнуто), жду")
                window, window_checked, first_check = found, now, False
            if window is None:
                time.sleep(1)
                continue
            try:
                grabbed = capturer.grab()
            except Exception as e:  # noqa: BLE001 - window moved or closed between checks
                log(f"снимок не удался: {e}")
                window = None
                continue
            if grabbed is None:
                time.sleep(config["poll_interval"])
                continue
            frame = protocol.decode(protocol.Image(*grabbed))
            if frame is None:
                misses += 1
                if protocol.last_failure == "damaged":
                    now = time.monotonic()
                    damaged_since = damaged_since or now
                    if not damaged_told and now - damaged_since > 1.0:
                        log("полоска видна, но кадры не читаются: её что-то перекрывает (миникарта, окно другого "
                            "аддона?) или настройки изображения искажают цвета")
                        damaged_told = True
                else:
                    damaged_since = None
                if linked and misses == int(5 / config["poll_interval"]):
                    log("полоска аддона пропала (выключен, свёрнут или скрыт интерфейс?)")
                    linked = False
            else:
                misses = 0
                damaged_since = None
                if not linked:
                    log(f"связь с аддоном есть (ячейка {frame.cell} px)")
                    linked = True
                if frame.seq != seen:
                    first = seen is None       # what was up before we started: not news
                    seen = frame.seq
                    line = protocol.parse(frame.payload)
                    if line and line.off is not None:
                        sapi.set_disabled({n for n in line.off.split("|") if n})
                    if line and line.voice:
                        engines.want(line.voice)
                    if line and line.kind == "control":
                        pass                                       # settings: applied above
                    elif line and line.kind == "regex":
                        regexes.receive(line.options, line.text)     # state, not speech: even if first
                    elif line and line.kind == "stop":
                        if not first:
                            engines.stop()
                            log("стоп: замолкаю")
                    elif line and line.kind == "reset" and not first:
                        engines.reset_assignments()
                    elif line and line.kind == "diag" and not first:
                        log(f"[диагностика аддона] {line.text}")
                    elif line and line.kind not in LABELS:
                        # a service line of a newer addon: never read aloud what is not chat
                        if line.kind not in unknown_kinds:
                            unknown_kinds.add(line.kind)
                            log(f"строки типа «{line.kind}» не озвучиваю (аддон новее программы?)")
                    elif line and line.text and not first:
                        text = MARKUP.sub("", line.text)
                        # the addon's replacements, then the regexes' (whose own patterns want plain
                        # text): each declined after its preposition when that is on
                        text = inflector.apply(text) if line.declension else strip_marks(text)
                        text = regexes.apply(text, mark=line.declension)
                        text = inflector.apply(text) if line.declension else strip_marks(text)
                        line = dataclasses.replace(line, text=text)
                        speaker = engines.for_line(line)
                        label = LABELS.get(line.kind, line.kind) + (f" {line.channel}" if line.channel else "")
                        log(f"[{label}] {line.sender} ({line.race or '?'}"
                            f"{', м' if line.sex == '2' else ', ж' if line.sex == '3' else ''})"
                            f" → {speaker.describe(line)}: {text}")
                        if config["log_details"] and line.raw and line.raw != text:
                            log(f"    исходно:   {line.raw}")
                        speaker.say(line)
            time.sleep(config["poll_interval"])


if __name__ == "__main__":
    sys.exit(main())
