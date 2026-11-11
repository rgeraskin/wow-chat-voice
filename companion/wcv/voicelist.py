"""The Windows voices, written into the addon as VoiceList.lua, so the addon can offer them (it
cannot ask Windows itself, and the program cannot talk to the game). WoW reads the file at start
and on /reload."""
from __future__ import annotations

from pathlib import Path

from .dictionary import wow_roots

ENGINES = {"edge": "Edge", "rhvoice": "RHVoice", "silero": "Silero", "other": "Windows"}


def find_addon(config: dict) -> Path | None:
    for root in wow_roots(config):
        path = root / "Interface" / "AddOns" / "WowChatVoice"
        if (path / "WowChatVoice.toc").exists():
            return path
    return None


def label(voice) -> str:
    name = voice.description
    for cut in (" - Russian (Russia)", " Online (Natural)", " (Russian)", " - Russian"):
        name = name.replace(cut, "")
    name = name.removeprefix("Microsoft ")
    return f"{name} ({ENGINES.get(voice.engine, voice.engine)})"


def _lua(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(voices, default_off) -> str:
    rows = [f"    {{ name = {_lua(v.description)}, label = {_lua(label(v))}, gender = {_lua(v.gender)}, "
            f"on = {'false' if default_off(v) else 'true'} }}," for v in voices]
    return ("-- Written by the WoW Chat Voice program: the Windows voices it can speak with.\n"
            "WowChatVoiceVoiceList = {\n" + "\n".join(rows) + "\n}\n")


def write(config: dict, voices, default_off, log) -> None:
    addon = find_addon(config)
    if addon is None:
        log("аддон WowChatVoice не найден: список голосов для него не записан")
        return
    path = addon / "VoiceList.lua"
    text = render(voices, default_off)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")
    log(f"список голосов Windows записан в аддон ({len(voices)}); в игре он появится после /reload")
