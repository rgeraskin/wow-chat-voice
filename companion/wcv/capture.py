"""Getting the strip's pixels off the WoW window.

Windows Graphics Capture (the `windows-capture` package, as OBS uses) reads the game's own window,
so it works while another window covers the game. When it is not available, a grab of that part of
the screen (mss) - which sees only what is on top. Neither sees a minimised game: WoW draws nothing
then.
"""
from __future__ import annotations

import threading
import time

from .window import find_wow_window, frame_offset


class WindowCapture:
    """Windows Graphics Capture of one window; the newest top strip kept for latest()."""

    def __init__(self, hwnd: int, client: tuple[int, int, int, int], height: int, log):
        from windows_capture import WindowsCapture

        self.hwnd, self.client, self.height, self.log = hwnd, client, height, log
        self.lock = threading.Lock()
        self.strip: tuple[bytes, int, int] | None = None
        self.stamp = 0.0
        self.closed = False
        self.offset = frame_offset(hwnd)
        self.session = WindowsCapture(cursor_capture=False, draw_border=False, minimum_update_interval=40,
                                      window_hwnd=hwnd)

        @self.session.event
        def on_frame_arrived(frame, control):
            if self.closed:
                control.stop()
                return
            buf = frame.frame_buffer                      # rows x columns x BGRA
            x, y = self.offset
            width = min(self.client[2], buf.shape[1] - x)
            rows = buf[y:y + self.height, x:x + width]
            with self.lock:
                self.strip = (rows.tobytes(), width, rows.shape[0])
                self.stamp = time.monotonic()

        @self.session.event
        def on_closed():
            self.closed = True

        self.session.start_free_threaded()

    def latest(self):
        with self.lock:
            return self.strip

    def stop(self) -> None:
        self.closed = True


class Capturer:
    """The strip of the current WoW window: Windows Graphics Capture when it works, else mss."""

    def __init__(self, config: dict, log):
        self.config, self.log = config, log
        self.height = config["capture_height"]
        self.window = None            # (hwnd, client rect)
        self.wgc: WindowCapture | None = None
        self.wgc_failed = not config.get("window_capture", True)
        self.screen = None

    def find(self):
        found = find_wow_window()
        if found != self.window:
            if self.wgc:
                self.wgc.stop()
                self.wgc = None
            self.window = found
            if found and not self.wgc_failed:
                try:
                    self.wgc = WindowCapture(found[0], found[1], self.height, self.log)
                    self.log("захват окна WoW: Windows Graphics Capture (работает и под другими окнами)")
                except Exception as e:  # noqa: BLE001 - fall back to grabbing the screen
                    self.wgc_failed = True
                    self.log(f"Windows Graphics Capture недоступен ({e}); снимаю экран — игра должна быть сверху")
        return found

    def grab(self):
        """(raw BGRA bytes, width, height) of the strip, or None."""
        if self.window is None:
            return None
        if self.wgc is not None:
            if self.wgc.closed:
                self.wgc = None
                self.window = None        # found again (and a new session made) on the next find()
                return None
            return self.wgc.latest()
        if self.screen is None:
            import mss
            self.screen = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        left, top, width, _ = self.window[1]
        shot = self.screen.grab({"left": left, "top": top, "width": width, "height": self.height})
        return bytes(shot.raw), shot.width, shot.height
