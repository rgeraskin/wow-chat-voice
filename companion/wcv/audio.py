"""One player for every engine: lines play strictly one after another (winsound stops a sound when
another starts, and two engines must never talk over or cut each other), each with a short silent
tail so the sound device does not clip the last syllable. stop() cuts the line being played and
drops everything queued or still being made (the "generation" a line was asked for in)."""
from __future__ import annotations

import io
import queue
import threading
import wave

TAIL = 0.25   # seconds of silence after each line


def wav(pcm: bytes, rate: int, volume: float = 1.0) -> bytes:
    """16-bit mono PCM as a WAV file in memory, scaled by `volume` (0..2; over 1 clipped - the
    engines go through f5engine.wav_bytes, which limits softly), with the silent tail."""
    if abs(volume - 1) > 0.001:
        import array
        samples = array.array("h", pcm)
        for i, s in enumerate(samples):
            samples[i] = max(-32768, min(32767, int(s * volume)))
        pcm = samples.tobytes()
    pcm += b"\0\0" * int(rate * TAIL)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


class Player(threading.Thread):
    """winsound cannot play from memory asynchronously (RuntimeError), and only an asynchronous
    sound can be cut: each line is written to a file first, a few names in turn."""

    def __init__(self, max_queue: int = 8, folder=None):
        super().__init__(daemon=True, name="player")
        import tempfile
        from pathlib import Path
        self.folder = Path(folder) if folder else Path(tempfile.gettempdir()) / "wow-chat-voice"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.turn = 0
        self.items: queue.Queue = queue.Queue()
        self.max_queue = max_queue
        self.generation = 0
        self.stopped = threading.Event()

    def play(self, data: bytes, generation: int | None = None) -> None:
        """Queue a line; one made for an earlier generation (before a stop) is dropped."""
        if generation is not None and generation != self.generation:
            return
        while self.items.qsize() >= self.max_queue:
            try:
                self.items.get_nowait()
            except queue.Empty:
                break
        self.items.put((self.generation, data))

    def stop(self) -> None:
        """Cut the line being played and forget the queue."""
        self.generation += 1
        while not self.items.empty():
            try:
                self.items.get_nowait()
            except queue.Empty:
                break
        self.stopped.set()

    def run(self) -> None:
        import winsound

        while True:
            generation, data = self.items.get()
            if generation != self.generation:
                continue
            self.stopped.clear()
            self.turn = (self.turn + 1) % 3
            path = self.folder / f"line{self.turn}.wav"
            path.write_bytes(data)
            # asynchronous, so a stop can cut it
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            if self.stopped.wait(seconds(data)):
                winsound.PlaySound(None, 0)
