"""Which voice each character speaks with (F5 engine): by race and sex, the same every time, and
different from the others of their race and sex heard lately while there are voices to go round."""
from __future__ import annotations

import json
import threading
import time
import zlib
from pathlib import Path

# The game's race file names (GetPlayerInfoByGUID's englishRace), lower case, to CatQuest's races.
RACES = {
    "human": "human", "orc": "orc", "dwarf": "dwarf", "nightelf": "nightelf", "scourge": "scourge",
    "undead": "scourge", "tauren": "tauren", "gnome": "gnome", "troll": "troll", "goblin": "goblin",
    "bloodelf": "bloodelf", "skyborne": "skyborne",
    # Races CatQuest has no voices for speak as their kin.
    "voidelf": "bloodelf", "nightborne": "nightelf", "lightforgeddraenei": "human", "draenei": "human",
    "worgen": "human", "kultiran": "human", "highmountaintauren": "tauren", "zandalaritroll": "troll",
    "magharorc": "orc", "darkirondwarf": "dwarf", "earthendwarf": "dwarf", "mechagnome": "gnome",
    "vulpera": "goblin", "pandaren": "dwarf", "dracthyr": "human", "haranir": "nightelf",
}
RECENT = 30 * 60   # seconds: characters heard within this count as "in the conversation"


class Assigner:
    def __init__(self, slots, path: Path, overrides: dict | None = None):
        self.slots = list(slots)
        self.by_id = {s.id: s for s in self.slots}
        self.path = path
        self.overrides = {k.lower(): v for k, v in (overrides or {}).items()}
        self.lock = threading.Lock()
        try:
            self.known = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.known = {}

    def _pool(self, race: str, sex: str):
        race = RACES.get(race.lower(), "human") if race else "human"
        sex = "female" if sex == "3" else "male"
        for r in (race, "human"):
            pool = [s for s in self.slots if s.race == r and s.sex == sex]
            if pool:
                return pool
        return [s for s in self.slots if s.race]

    def slot_for(self, sender: str, race: str, sex: str, now: float | None = None):
        with self.lock:
            return self._slot_for(sender, race, sex, now)

    def _slot_for(self, sender: str, race: str, sex: str, now: float | None = None):
        """The voice slot for `sender`: an override, else the one given before (if it still fits
        their race and sex), else the least used among those heard lately - the pack's own voices
        before the pitch-shifted copies, ties broken by the name so the choice is stable."""
        now = time.time() if now is None else now
        key = sender.lower()
        short = key.split("-")[0]
        override = self.overrides.get(key) or self.overrides.get(short)
        if override and override in self.by_id:
            return self.by_id[override]
        pool = self._pool(race, sex)
        if not pool:
            return None
        ids = {s.id for s in pool}
        entry = self.known.get(key)
        if entry and entry.get("slot") in ids:
            entry["seen"] = now
            self._save()
            return self.by_id[entry["slot"]]
        used: dict[str, int] = {}
        for other, e in self.known.items():
            if other != key and e.get("slot") in ids and now - e.get("seen", 0) < RECENT:
                used[e["slot"]] = used.get(e["slot"], 0) + 1
        offset = zlib.crc32(key.encode("utf-8"))
        ordered = sorted(pool, key=lambda s: (used.get(s.id, 0), s.shift != 0,
                                              (pool.index(s) + offset) % len(pool)))
        slot = ordered[0]
        self.known[key] = {"slot": slot.id, "seen": now}
        self._save()
        return slot

    def reset(self) -> None:
        """Forget who had which voice: everyone gets one afresh as they speak."""
        with self.lock:
            self.known = {}
            self._save()

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.known, ensure_ascii=False, indent=0), encoding="utf-8")
        except OSError:
            pass
