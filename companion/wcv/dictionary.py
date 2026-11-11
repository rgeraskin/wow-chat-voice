"""The addon dictionary's regular expressions ("~pattern=replacement" lines), applied here in Python:
read from the addon's saved variables, which the game writes on /reload and on logout.

The rest of the dictionary (words, phrases, stems) is applied by the addon itself.
"""
from __future__ import annotations

import re
from pathlib import Path

SAVED = "WowChatVoice.lua"
# The merged regexes the addon keeps for us in its saved variables (its dictionary itself is saved
# as edits of the default).
LUA_REGEXES = re.compile(r'\["regexes"\]\s*=\s*"((?:[^"\\]|\\.)*)"', re.S)
LUA_ESCAPE = re.compile(r'\\(\d{1,3}|.)', re.S)
SIMPLE = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def unescape(body: str) -> str:
    """A Lua string literal's body as text (the game writes \\n, \\", \\\\ and \\ddd byte escapes)."""
    raw = bytearray()
    pos = 0
    for m in LUA_ESCAPE.finditer(body):
        raw += body[pos:m.start()].encode("utf-8")
        code = m.group(1)
        if code.isdigit():
            raw.append(int(code) & 0xFF)
        else:
            raw += SIMPLE.get(code, code).encode("utf-8")
        pos = m.end()
    raw += body[pos:].encode("utf-8")
    return raw.decode("utf-8", "replace")


def wow_roots(config: dict) -> list[Path]:
    """Game folders (_forever_, _retail_) of the configured and the usual WoW installs."""
    roots = [Path(config["wow_dir"])] if config.get("wow_dir") else []
    for drive in "CDEFGH":
        for base in (f"{drive}:/World of Warcraft", f"{drive}:/Games/World of Warcraft",
                     f"{drive}:/Program Files (x86)/World of Warcraft"):
            roots += [Path(base) / "_forever_", Path(base) / "_retail_"]
    return roots


def find_saved(config: dict) -> Path | None:
    """The newest WowChatVoice.lua under WTF/Account/*/SavedVariables of the WoW installs we know."""
    found = []
    for root in wow_roots(config):
        account = root / "WTF" / "Account"
        if account.is_dir():
            found += [p for p in account.glob(f"*/SavedVariables/{SAVED}") if p.is_file()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


PLURAL = re.compile(r"(\d+)(\s*)\[([^\[\]|]+)\|([^\[\]|]+)\|([^\[\]|]+)\]")


def plural_form(n: int, one: str, few: str, many: str) -> str:
    """Russian noun form after a number: 1, 21 - one; 2-4, 22-24 - few; 0, 5-20, 25-30 - many."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


ORDINAL = re.compile(r"<(\d{1,4})>")


def ordinals(text: str) -> str:
    """"<60>" -> "шестидесятый" (num2words; the declension after a preposition comes later)."""
    try:
        from num2words import num2words
    except ImportError:
        return ORDINAL.sub(r"\1", text)
    return ORDINAL.sub(lambda m: num2words(int(m.group(1)), lang="ru", to="ordinal"), text)


def plurals(text: str) -> str:
    """"5 [дамагер|дамагера|дамагеров]" -> "5 дамагеров" (written by the dictionary's regexes)."""
    return PLURAL.sub(lambda m: m.group(1) + (m.group(2) or " ")
                      + plural_form(int(m.group(1)), m.group(3), m.group(4), m.group(5)), text)


def parse(dictionary: str, log) -> list[tuple[re.Pattern, str]]:
    rules = []
    for line in dictionary.splitlines():
        line = line.strip()
        if not line.startswith("~") or "=" not in line:
            continue
        pattern, replacement = line[1:].rsplit("=", 1)
        try:
            rules.append((re.compile(pattern.strip(), re.IGNORECASE), replacement.strip()))
        except re.error as e:
            log(f"словарь: регулярка «{pattern}» с ошибкой: {e}")
    return rules


class Regexes:
    def __init__(self, config: dict, log):
        self.config, self.log = config, log
        self.path: Path | None = None
        self.stamp = None
        self.rules: list[tuple[re.Pattern, str]] = []
        self.from_addon: str | None = None        # id of the set the addon sent over the strip
        self.parts: dict[str, dict[int, str]] = {}

    def receive(self, options: dict, text: str) -> None:
        """A part of the regex set sent by the addon ("id=..;part=i;of=n"); used once complete.
        From then on the saved variables (stale until the next /reload) are not read."""
        set_id, part, total = options.get("id", ""), options.get("part", ""), options.get("of", "")
        if not (set_id and part.isdigit() and total.isdigit()):
            return
        if set_id == self.from_addon:
            return                                # resent unchanged (every 2 minutes, when edited this session)
        parts = self.parts.setdefault(set_id, {})
        parts[int(part)] = text
        if len(parts) < int(total):
            return
        joined = "\n".join(parts[i] for i in sorted(parts))
        self.parts = {}
        self.rules = parse("" if joined == "-" else joined, self.log)
        self.from_addon = set_id
        self.log(f"словарь: регулярок {len(self.rules)} (из игры)")

    def refresh(self) -> None:
        """Re-read the saved variables when they changed (cheap: a stat call) - only until the
        addon has sent its regexes over the strip."""
        if self.from_addon:
            return
        path = self.path if self.path and self.path.exists() else find_saved(self.config)
        if path is None:
            return
        stamp = path.stat().st_mtime
        if path == self.path and stamp == self.stamp:
            return
        self.path, self.stamp = path, stamp
        saved = path.read_text(encoding="utf-8", errors="replace")
        match = LUA_REGEXES.search(saved)
        rules = parse(unescape(match.group(1)), self.log) if match else []
        if [p.pattern for p, _ in rules] != [p.pattern for p, _ in self.rules] or not self.rules:
            self.log(f"словарь: регулярок {len(rules)} ({path})")
        self.rules = rules

    def apply(self, text: str, mark: bool = False) -> str:
        """`text` through the regexes; with `mark`, each replacement wrapped in \\x02...\\x03 so it
        can be declined after a preposition, like the addon's replacements."""
        for pattern, replacement in self.rules:
            try:
                if mark:
                    text = pattern.sub(lambda m, r=replacement: "\x02" + m.expand(r) + "\x03", text)
                else:
                    text = pattern.sub(replacement, text)
            except (re.error, IndexError) as e:
                self.log(f"словарь: замена «{replacement}»: {e}")
        return plurals(ordinals(text))
