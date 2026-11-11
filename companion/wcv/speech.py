"""Speaking chat lines with Windows SAPI 5 voices, one voice per sender."""
from __future__ import annotations

import math
import queue
import re
import threading
import zlib

from .audio import Player, wav
from .text import Accentor, apply_stress

SVSF_IS_NOT_XML = 16
RUSSIAN = "419"
ENGLISH = {"409", "809", "c09", "1009", "4009"}   # US, UK, Australia, Canada, India
CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
LATIN = re.compile(r"[A-Za-z]")


def is_english(text: str) -> bool:
    """A line in Latin letters only (until a version knows other languages): read by English voices."""
    return bool(LATIN.search(text)) and not CYRILLIC.search(text)
SAFT22K16BIT_MONO = 22      # SpeechAudioFormatType: what lines are rendered into
RENDER_RATE = 22050
CHARS_PER_SECOND = 16       # Russian at normal speed is ~14 characters a second; a little slack


def pick(sender: str, pool: list) -> "Voice | None":
    """The voice for `sender`: the highest hash of (name, voice) - rendezvous hashing. Switching a
    voice off moves only the people who had it; everyone else keeps theirs (a hash modulo the pool
    size would move almost everyone)."""
    if not pool:
        return None
    key = sender.lower()
    return max(pool, key=lambda v: zlib.crc32(f"{key}|{v.description}".encode("utf-8")))


def sapi_rate(base: int, percent: int) -> int:
    """SAPI's rate (-10..10, +10 is about three times as fast) for `percent` of normal speed."""
    return max(-10, min(10, base + round(10 * math.log(max(percent, 1) / 100) / math.log(3))))


class Voice:
    def __init__(self, token, description: str, gender: str, engine: str):
        self.token, self.description, self.gender, self.engine = token, description, gender, engine

    def __repr__(self):
        return f"{self.description} [{self.gender}, {self.engine}]"


def _attribute(token, name: str) -> str:
    try:
        return token.GetAttribute(name) or ""
    except Exception:  # noqa: BLE001 - COM raises when the attribute is missing
        return ""


def _engine(token) -> str:
    if _attribute(token, "NaturalVoiceType"):
        return "edge"
    vendor = _attribute(token, "Vendor").lower()
    if "silero" in vendor:
        return "silero"
    if "yakovleva" in vendor or "rhvoice" in vendor:
        return "rhvoice"
    return "other"


class Speaker(threading.Thread):
    """Owns the SAPI objects (COM wants them on one thread) and speaks queued lines in order."""

    def __init__(self, config: dict, log, accentor: Accentor | None = None, player: Player | None = None):
        super().__init__(daemon=True, name="speaker")
        self.config, self.log = config, log
        self.player = player
        self.accentor = accentor or Accentor(log, config.get("ruaccent", True))
        self.lines: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self.voices: list[Voice] = []
        self.all_voices: list[Voice] = []
        self.english: list[Voice] = []

    # --- voice pool -------------------------------------------------------------------------

    def _load_voices(self, sapi) -> None:
        overrides = {k.lower(): v for k, v in self.config["gender_overrides"].items()}
        voices, english = [], []
        tokens = sapi.GetVoices()
        for i in range(tokens.Count):
            token = tokens.Item(i)
            description = token.GetDescription()
            languages = {code.lower() for code in _attribute(token, "Language").split(";")}
            if RUSSIAN not in languages:
                if languages & ENGLISH:
                    gender = (_attribute(token, "Gender") or "Neutral").capitalize()
                    english.append(Voice(token, description, gender, _engine(token)))
                continue
            gender = _attribute(token, "Gender") or "Neutral"
            for prefix, value in overrides.items():
                if description.lower().startswith(prefix):
                    gender = value
            voices.append(Voice(token, description, gender.capitalize(), _engine(token)))
        voices.sort(key=lambda v: v.description.lower())
        # Natural (online) English voices first; the old desktop ones only when there is nothing else.
        english.sort(key=lambda v: ("desktop" in v.description.lower(), v.description.lower()))
        self.english = [v for v in english if "desktop" not in v.description.lower()] or english
        self.all_voices = voices
        self.set_disabled(None)

    def default_off(self, voice: Voice) -> bool:
        return any(e.lower() in voice.description.lower() for e in self.config["exclude"])

    def set_disabled(self, names: set[str] | None) -> None:
        """Voices switched off in the addon (by description); None: config.json's exclude list."""
        if names is None:
            on = [v for v in self.all_voices if not self.default_off(v)]
        else:
            on = [v for v in self.all_voices if v.description not in names]
        self.voices = on or self.all_voices

    def pool(self, sex: str) -> list[Voice]:
        wanted = {"2": "Male", "3": "Female"}.get(sex)
        if wanted:
            matching = [v for v in self.voices if v.gender == wanted]
            if matching:
                return matching
        return self.voices

    def voice_for(self, sender: str, sex: str, forced: str = "", text: str = "") -> Voice | None:
        if forced:
            for v in self.all_voices:
                if v.description == forced:
                    return v
        if text and self.english and is_english(text):
            wanted = {"2": "Male", "3": "Female"}.get(sex)
            return pick(sender, [v for v in self.english if v.gender == wanted] or self.english)
        override = self.config["players"].get(sender) or self.config["players"].get(sender.split("-")[0])
        if override:
            for v in self.voices:
                if override.lower() in v.description.lower():
                    return v
        return pick(sender, self.pool(sex))

    def fallback_for(self, sender: str, sex: str, failed: Voice) -> Voice | None:
        """A voice of the same sex on another engine, for when `failed` gives no audio."""
        pool = [v for v in self.pool(sex) if v.engine != failed.engine] or \
               [v for v in self.voices if v.engine != failed.engine]
        return pick(sender, pool)

    # --- queue ------------------------------------------------------------------------------

    def describe(self, line) -> str:
        voice = self.voice_for(line.sender, line.sex, line.sapi_voice, line.text)
        return voice.description if voice else "-"

    def clear(self) -> None:
        while not self.lines.empty():
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break

    def say(self, line) -> None:
        while self.lines.qsize() >= self.config["max_queue"]:
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break
        self.lines.put(line)

    def _even(self, pcm: bytes, kind: str, volume: float) -> bytes:
        """The same loudness for every engine (RHVoice, Silero and Edge differ a lot), a yell
        louder, a whisper quieter - one gain for the whole line."""
        try:
            import numpy as np
            from .f5engine import wav_bytes
        except ImportError:
            return wav(pcm, RENDER_RATE, volume)
        samples = np.frombuffer(pcm, dtype="<i2").astype("float32") / 32768
        return wav_bytes(samples, RENDER_RATE, volume,
                         self.config["kind_gain_db"].get(kind, 0))

    def _render(self, sapi, voice: Voice, text: str, rate: int = 100) -> bytes | None:
        """`text` spoken by `voice` as 22 kHz 16-bit PCM; None when the audio is missing or much
        shorter than the text needs (Edge sometimes drops the connection mid-line)."""
        import win32com.client

        memory = win32com.client.Dispatch("SAPI.SpMemoryStream")
        memory.Format.Type = SAFT22K16BIT_MONO
        sapi.AudioOutputStream = memory
        sapi.Voice = voice.token
        sapi.Rate = sapi_rate(self.config["rate"], rate)
        sapi.Speak(apply_stress(text, self.config["stress"].get(voice.engine, "strip")), SVSF_IS_NOT_XML)
        pcm = bytes(memory.GetData())
        seconds = len(pcm) / (RENDER_RATE * 2)
        expected = len(text) / CHARS_PER_SECOND * 100 / max(rate, 1)
        if seconds < 0.2 or seconds < 0.45 * expected:
            if seconds >= 0.2:
                self.log(f"{voice.description}: звук оборван ({seconds:.1f} с из ~{expected:.1f} с)")
            return None
        return pcm

    def run(self) -> None:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        sapi = win32com.client.Dispatch("SAPI.SpVoice")
        if self.player is None:
            self.player = Player(self.config["max_queue"])
            self.player.start()
        self._load_voices(sapi)
        self.accentor.load()
        self.ready.set()
        while True:
            line = self.lines.get()
            generation = self.player.generation      # a stop while this is being made drops it
            sender, sex = line.sender, line.sex
            text = self.accentor.accent(line.text)
            voice = self.voice_for(sender, sex, line.sapi_voice, text)
            if voice is None:
                self.log("нет ни одного русского голоса SAPI")
                continue
            attempts = [voice] * (2 if voice.engine == "edge" else 1)
            alternative = None if line.sapi_voice else self.fallback_for(sender, sex, voice)
            if alternative:
                attempts.append(alternative)
            if self.config.get("log_details"):
                final = apply_stress(text, self.config["stress"].get(voice.engine, "strip"))
                if final != line.text:
                    self.log(f"    к синтезу: {final}")
            for attempt in attempts:
                try:
                    audio = self._render(sapi, attempt, text, line.rate)
                except Exception as e:  # noqa: BLE001 - one bad voice must not stop the reader
                    self.log(f"ошибка голоса {attempt.description}: {e}")
                    audio = None
                if audio is None:
                    self.log(f"{attempt.description}: нет звука")
                    continue
                if attempt is not voice:
                    self.log(f"  вместо него: {attempt.description}")
                self.player.play(self._even(audio, line.kind, line.gain(self.config)), generation)
                break


def selftest(config: dict, log) -> None:
    """Render a test line with one voice of each engine into memory and report the audio size."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    speaker = Speaker(config, log)
    sapi = win32com.client.Dispatch("SAPI.SpVoice")
    speaker._load_voices(sapi)
    seen = set()
    for voice in speaker.voices:
        if voice.engine in seen:
            continue
        seen.add(voice.engine)
        audio = speaker._render(sapi, voice, "Нужен дам+агер в пещеры, продам сумки.")
        size = len(audio) if audio else 0
        log(f"{voice.engine:8s} {voice.description}: {size} байт" + ("" if audio else " - НЕТ ЗВУКА"))
