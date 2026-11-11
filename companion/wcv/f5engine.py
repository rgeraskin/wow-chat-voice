"""F5-TTS (Russian fine-tune) speaking chat lines in CatQuest's race voices, on the GPU.

One thread synthesises, another plays, so the next line is ready while one is being said.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import queue
import threading
import time
import wave
from pathlib import Path

from .assign import Assigner
from .audio import Player, wav
from .catquest import build, find_pack
from .intonation import shape
from .text import Accentor, numbers_to_words

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
GAP = 0.15   # seconds between sentence groups made separately


def sentence_groups(text: str) -> list[str]:
    """`text` cut into runs of statements and single questions, so each question can get its own
    intonation: "Привет. Кто идёт? Есть хил? Собираемся у входа." is four runs."""
    groups: list[str] = []
    last = None
    for sentence in SENTENCE_END.split(text.strip()):
        if not sentence:
            continue
        question = sentence.rstrip().endswith("?")
        if groups and not question and last is False:
            groups[-1] += " " + sentence
        else:
            groups.append(sentence)
        last = question
    return groups or [text]

MODEL_REPO = "Misha24-10/F5-TTS_RUSSIAN"
MODEL_FILE = "F5TTS_v1_Base_v2/model_last_inference.safetensors"
VOCAB_FILE = "F5TTS_v1_Base/vocab.txt"


TARGET_RMS = 0.08     # about -22 dBFS: every voice about as loud as the others
PEAK = 0.95


def tidy(samples, rate: int, gain_db: float = 0.0):
    """Speech with the silence before it cut (keeping 50 ms) and its loudness evened out: to
    TARGET_RMS, `gain_db` louder or quieter (a yell, a whisper), never over PEAK. One gain for the
    whole line, so the intonation inside it is kept."""
    import numpy as np

    samples = np.asarray(samples, dtype="float32")
    if not len(samples):
        return samples
    peak = float(np.max(np.abs(samples))) or 1.0
    loud = np.flatnonzero(np.abs(samples) > peak * 0.03)  # about -30 dB under the peak
    if len(loud):
        samples = samples[max(0, loud[0] - rate // 20):]  # keep 50 ms before the first sound
    rms = float(np.sqrt(np.mean(samples ** 2))) or 1e-6
    gain = TARGET_RMS * 10 ** (gain_db / 20) / rms
    peak = float(np.max(np.abs(samples))) or 1e-6
    gain = min(gain, PEAK / peak)
    return samples * gain


KNEE = 0.8   # peaks above this are bent smoothly toward full scale instead of clipped


def limit(samples):
    """Peaks over KNEE eased toward 1.0 (tanh) instead of cut off: a line played louder than 100 %
    (the addon's volume goes to 200 %) stays clean; below KNEE nothing changes."""
    import numpy as np

    a = np.abs(samples)
    over = a > KNEE
    if not over.any():
        return samples
    out = np.array(samples, dtype="float32")
    out[over] = np.sign(out[over]) * (KNEE + (1 - KNEE) * np.tanh((a[over] - KNEE) / (1 - KNEE)))
    return out


def wav_bytes(samples, rate: int, volume: float, gain_db: float = 0.0) -> bytes:
    import numpy as np

    samples = limit(tidy(samples, rate, gain_db) * volume)
    return wav((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes(), rate)


class F5Speaker:
    def __init__(self, config: dict, log, home: Path, accentor: Accentor | None = None,
                 player: Player | None = None):
        self.config, self.log, self.home = config, log, home
        self.player = player
        self.lines: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self.error: str | None = None
        self.accentor = accentor or Accentor(log, config.get("ruaccent", True))
        self.assigner: Assigner | None = None
        self.tts = None
        self.ref_text: dict[str, str] = {}

    # --- setup (on the synth thread) --------------------------------------------------------

    def _load(self) -> None:
        if self.config.get("hf_home"):
            os.environ["HF_HOME"] = self.config["hf_home"]
        import soundfile as sf
        import torch
        import torchaudio

        if not torch.cuda.is_available():
            raise RuntimeError("нет видеокарты NVIDIA с CUDA")

        def load_audio(path, *a, **k):   # torchaudio 2.11 decodes through torchcodec (FFmpeg DLLs)
            data, rate = sf.read(str(path), dtype="float32", always_2d=True)
            return torch.from_numpy(data.T.copy()), rate
        torchaudio.load = load_audio

        pack = find_pack(self.config)
        if pack is None:
            raise RuntimeError("не найден аддон CatQuest_Voices (укажите catquest_dir в config.json)")
        made = []

        def make_checker():               # Whisper only if the bank is actually (re)built
            from .refcheck import Checker
            checker = Checker(self.log)
            if checker.load():
                made.append(checker)
                return checker
            return None

        slots = build(pack, self.home / "voices", self.config["voice_shifts"], self.log,
                      make_checker if self.config.get("check_refs", True) else None)
        if made:
            made.clear()                  # free Whisper's GPU memory before F5 loads
            import gc
            gc.collect()
            torch.cuda.empty_cache()
        self.assigner = Assigner(slots, self.home / "assignments.json", self.config["players"])

        self.log("загружаю RUAccent ...")
        self.accentor.load()
        self.log("загружаю F5-TTS ...")
        from huggingface_hub import hf_hub_download
        from f5_tts.api import F5TTS

        # F5 prints "Download Vocos from huggingface" every time, though it takes it from the cache
        with contextlib.redirect_stdout(io.StringIO()):
            self.tts = F5TTS(model="F5TTS_v1_Base", ckpt_file=hf_hub_download(MODEL_REPO, MODEL_FILE),
                             vocab_file=hf_hub_download(MODEL_REPO, VOCAB_FILE), device="cuda")
        offline = os.environ.get("HF_HUB_OFFLINE") == "1"
        self.log("модели F5 и Vocos: " + ("из кэша, без сети" if offline else "из кэша Hugging Face (с проверкой обновлений)"))
        self.ref_text = {s.id: self.accentor.accent(s.text) for s in slots}
        self.ref_seconds = {s.id: sf.info(s.path).duration for s in slots}
        self.q_text = {s.id: self.accentor.accent(s.q_text) for s in slots if s.q_path}
        self.q_seconds = {s.id: sf.info(s.q_path).duration for s in slots if s.q_path}
        first = next(s for s in slots if s.race)
        self._synth(first, "Проверка.", 100)   # warm-up: the first call is slow
        self.log(f"F5-TTS готов на {torch.cuda.get_device_name(0)}")

    def reference(self, slot, text: str):
        """(clip, its text, its seconds): the question clip for a line ending in "?" - F5 takes the
        intonation from the reference, and a statement clip makes questions sound flat."""
        if self.config.get("f5_question_refs") and text.rstrip().endswith("?") and slot.id in self.q_text:
            return slot.q_path, self.q_text[slot.id], self.q_seconds[slot.id]
        return slot.path, self.ref_text[slot.id], self.ref_seconds[slot.id]

    def duration(self, slot, text: str, rate: int) -> float:
        """Total seconds (reference + line) to give F5. Its own estimate - the reference's pace in
        bytes of text - cuts the last syllables when the reference is spoken fast, so a margin."""
        _, ref_text, ref = self.reference(slot, text)
        pace = ref / max(1, len(ref_text.encode("utf-8")))
        line = pace * len(text.encode("utf-8")) / (rate / 100)
        return ref + line * self.config["f5_margin"] + self.config["f5_tail"]

    def _synth(self, slot, text: str, rate: int):
        with contextlib.redirect_stdout(io.StringIO()):   # F5 prints ref_text/gen_text for each call
            ref_file, ref_text, _ = self.reference(slot, text)
            wav, sr, _ = self.tts.infer(ref_file=ref_file, ref_text=ref_text, gen_text=text,
                                        nfe_step=self.config["nfe_step"], speed=rate / 100,
                                        fix_duration=self.duration(slot, text, rate),
                                        show_info=lambda *a: None, progress=None)
        return wav, sr

    # --- threads ----------------------------------------------------------------------------

    def start(self) -> None:
        if self.player is None:
            self.player = Player(self.config["max_queue"])
            self.player.start()
        threading.Thread(target=self._synth_loop, daemon=True, name="f5-synth").start()

    def _synth_loop(self) -> None:
        try:
            self._load()
        except Exception as e:  # noqa: BLE001 - reported, the caller falls back to SAPI
            self.error = str(e)
            self.ready.set()
            return
        self.ready.set()
        while True:
            line = self.lines.get()
            if line is None:                 # shutdown: free the model and the GPU memory
                self.tts = None
                import gc
                import torch
                gc.collect()
                torch.cuda.empty_cache()
                return
            generation = self.player.generation   # a stop while this is being made drops it
            slot = self.assigner.slot_for(line.sender, line.race, line.sex)
            if slot is None:
                continue
            text = numbers_to_words(self.accentor.accent(line.text))
            if text[-1:].isalnum() or text[-1:] == "+":
                text += "."
            if self.config.get("log_details") and text != line.text:
                groups = sentence_groups(text)
                self.log(f"    к синтезу: {text}" + (f"  ({len(groups)} части)" if len(groups) > 1 else ""))
            started = time.perf_counter()
            try:
                import numpy as np
                pieces, sr = [], 24000
                for group in sentence_groups(text):
                    piece, sr = self._synth(slot, group, line.rate)
                    piece = shape(piece, sr, group, self.config.get("question_intonation"))
                    if pieces:
                        pieces.append(np.zeros(int(sr * GAP), dtype=piece.dtype))
                    pieces.append(piece)
                    if generation != self.player.generation:
                        break                       # stopped meanwhile: no need to finish
                wav = np.concatenate(pieces)
            except Exception as e:  # noqa: BLE001 - one bad line must not stop the reader
                self.log(f"F5-TTS: {e}")
                continue
            if self.config.get("debug"):
                self.log(f"  синтез {time.perf_counter() - started:.2f} с, {len(wav) / sr:.1f} с звука")
            gain = self.config["kind_gain_db"].get(line.kind, 0)
            self.player.play(wav_bytes(wav, sr, line.gain(self.config), gain), generation)

    # --- the reader's side ------------------------------------------------------------------

    def describe(self, line) -> str:
        if self.assigner is None:
            return "-"
        slot = self.assigner.slot_for(line.sender, line.race, line.sex)
        return slot.id if slot else "-"

    def clear(self) -> None:
        while not self.lines.empty():
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        """Stop after the line being made; the model is freed on the synth thread."""
        while not self.lines.empty():
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break
        self.lines.put(None)

    def say(self, line) -> None:
        while self.lines.qsize() >= self.config["max_queue"]:
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break
        self.lines.put(line)


def selftest(config: dict, log, home: Path) -> int:
    """Build the voice bank and synthesise a line for a few characters into home/f5test, timed."""
    import soundfile as sf
    from .protocol import Line

    speaker = F5Speaker(config, log, home)
    speaker._load()
    out = home / "f5test"
    out.mkdir(exist_ok=True)
    cast = [("Громмаш", "Orc", "2"), ("Гаррош", "Orc", "2"), ("Дрекша", "Orc", "3"), ("Джайна", "Human", "3"),
            ("Брэнн", "Dwarf", "2"), ("Тиранда", "NightElf", "3"), ("Вол'джин", "Troll", "2"), ("Сильвана", "Scourge", "3")]
    for name, race, sex in cast:
        line = Line("test", name, race, sex, "", "", "Нужен дд в Мёртвые копи, продам сумки за 5000.")
        slot = speaker.assigner.slot_for(name, race, sex)
        text = numbers_to_words(speaker.accentor.accent(line.text))
        started = time.perf_counter()
        wav, sr = speaker._synth(slot, text, 100)
        took = time.perf_counter() - started
        sf.write(str(out / f"{race}_{name}.wav"), wav, sr)
        log(f"{name:9s} {race:8s} -> {slot.id:22s} {took:.2f} с на {len(wav) / sr:.1f} с звука")
    import ctypes
    import torch

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    c = Counters()
    c.cb = ctypes.sizeof(c)
    kernel32.K32GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    log(f"память: {c.WorkingSetSize / 2**30:.2f} ГБ (пик {c.PeakWorkingSetSize / 2**30:.2f}), "
        f"видеопамять: {torch.cuda.max_memory_reserved() / 2**30:.2f} ГБ")
    log(f"файлы: {out}")
    return 0
