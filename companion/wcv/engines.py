"""Which engine speaks: Windows voices (always loaded, light) or F5-TTS race voices (loaded only
while the addon asks for them, unloaded when it asks for Windows voices). Notices go to the
program's window; spoken only with "spoken_notices" (the program cannot write into the game)."""
from __future__ import annotations

import threading
from pathlib import Path

from .protocol import Line

NOTICE_SENDER = "WoW Chat Voice"


class Engines:
    def __init__(self, config: dict, log, home: Path, sapi, accentor, player=None):
        self.config, self.log, self.home = config, log, home
        self.player = player
        self.sapi, self.accentor = sapi, accentor
        self.f5 = None
        self.ready = False
        self.on_ready = None    # called once F5 is loaded (all models are in the cache by then)
        self.on_error = None    # called with the error when F5 fails to load
        self.lock = threading.Lock()

    def notice(self, text: str) -> None:
        self.log(text)
        if self.config.get("spoken_notices"):
            self.sapi.say(Line("notice", NOTICE_SENDER, "", "3", "", "", text))

    def want(self, voice: str) -> None:
        """The addon's choice of voices: load F5 for "f5", unload it for "sapi"."""
        if voice == "f5":
            self._load()
        elif voice == "sapi":
            self._unload()

    def _load(self) -> None:
        with self.lock:
            if self.f5 is not None:
                return
            from .f5engine import F5Speaker
            self.log("загружаю голоса рас (F5-TTS) ...")
            speaker = F5Speaker(self.config, self.log, self.home, self.accentor, self.player)
            self.f5, self.ready = speaker, False
            speaker.start()
        threading.Thread(target=self._wait, args=(speaker,), daemon=True, name="f5-wait").start()

    def _wait(self, speaker) -> None:
        speaker.ready.wait()
        with self.lock:
            if self.f5 is not speaker:
                return                      # unloaded meanwhile
            if speaker.error:
                self.f5 = None
                error = speaker.error
            else:
                self.ready, error = True, None
        if error:
            self.notice("Голоса рас недоступны, читаю голосами Windows.")
            self.log(f"  причина: {error}")
            if self.on_error:
                self.on_error(error)
        else:
            self.notice("Голоса рас готовы.")
            if self.on_ready:
                self.on_ready()

    def _unload(self) -> None:
        with self.lock:
            speaker, was_ready = self.f5, self.ready
            self.f5, self.ready = None, False
        if speaker is None:
            return
        speaker.shutdown()
        if was_ready:
            self.notice("Голоса рас выгружены.")
        else:
            self.log("загрузка голосов рас отменена")

    def stop(self) -> None:
        """Silence now: the line being played is cut, the queues and lines being made dropped."""
        self.sapi.clear()
        with self.lock:
            speaker = self.f5
        if speaker is not None:
            speaker.clear()
        if self.player is not None:
            self.player.stop()

    def reset_assignments(self) -> None:
        """The addon's "hand the race voices out afresh"."""
        with self.lock:
            speaker = self.f5
        if speaker is not None and speaker.assigner is not None:
            speaker.assigner.reset()
        else:
            (self.home / "assignments.json").unlink(missing_ok=True)
        self.log("голоса рас будут розданы заново")

    def for_line(self, line: Line):
        """The engine for a chat line: F5 when the line asks for it and it is ready (starting it if
        need be; meanwhile Windows voices), else SAPI."""
        voice = line.voice or self.config["engine"]
        if voice == "f5":
            self._load()
            with self.lock:
                if self.ready and self.f5 is not None:
                    return self.f5
        return self.sapi
