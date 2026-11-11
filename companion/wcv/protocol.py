"""Decoder for the addon's pixel strip (addon/WowChatVoice/Protocol.lua, README "Protocol").

Standard library only, so the round-trip test runs anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VERSION = 1
HEADER_CELLS = 6
HEADER_BITS = 48
BITS_PER_CELL = 6
MAX_CELL = 8          # largest cell size (physical pixels) looked for
MIN_LEVEL_GAP = 4     # calibration levels closer than this (0..255) are not trusted (the addon's are 12 apart)


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class Frame:
    seq: int
    payload: bytes
    cell: int


class Image:
    """A BGRA screen grab: `raw` bytes, `width` x `height` pixels; `mirrored` reads it right to
    left (the addon draws its cells from the right edge by default)."""

    def __init__(self, raw: bytes, width: int, height: int, mirrored: bool = False):
        self.raw, self.width, self.height, self.mirrored = raw, width, height, mirrored

    def rgb(self, x: int, y: int) -> tuple[int, int, int]:
        if self.mirrored:
            x = self.width - 1 - x
        i = (y * self.width + x) * 4
        return self.raw[i + 2], self.raw[i + 1], self.raw[i]


def _close(a, b, tol=10) -> bool:
    return all(abs(p - q) <= tol for p, q in zip(a, b))


def _cell_size(img: Image) -> int | None:
    """The cell size: the run of the first sync cell's colour along the top row."""
    first = img.rgb(0, 0)
    r, g, b = first
    if not (r > g + MIN_LEVEL_GAP and b > g + MIN_LEVEL_GAP):
        return None
    size = 1
    while size <= MAX_CELL and size < img.width and _close(img.rgb(size, 0), first):
        size += 1
    return size if size <= MAX_CELL else None


# Why the last decode() found no frame: "absent" (no strip there) or "damaged" (a strip - sync and
# calibration cells in place - whose frame does not check out: something drawn over it?).
last_failure = ""


def decode(img: Image) -> Frame | None:
    """The frame on the strip at the top of `img` - drawn from the left edge or the right - or None
    when there is none (or it is damaged; see `last_failure`)."""
    global last_failure
    damaged = False
    for mirrored in (False, True):
        frame, synced = _decode(Image(img.raw, img.width, img.height, mirrored))
        if frame is not None:
            last_failure = ""
            return frame
        damaged = damaged or synced
    last_failure = "damaged" if damaged else "absent"
    return None


def _decode(img: Image) -> tuple[Frame | None, bool]:
    """(the frame or None, whether the sync and calibration cells were there)."""
    cell = _cell_size(img)
    if not cell:
        return None, False
    per_row = img.width // cell
    rows = img.height // cell
    if per_row < HEADER_CELLS + 8 or rows < 1:
        return None, False

    def sample(i: int) -> tuple[int, int, int]:
        row, col = divmod(i, per_row)
        return img.rgb(col * cell + cell // 2, row * cell + cell // 2)

    calib = [sample(HEADER_CELLS - 4 + k) for k in range(4)]
    thresholds = []
    for ch in range(3):
        levels = [c[ch] for c in calib]
        if any(levels[k + 1] - levels[k] < MIN_LEVEL_GAP for k in range(3)):
            return None, False
        thresholds.append([(levels[k] + levels[k + 1]) / 2 for k in range(3)])

    def classify(value: int, ch: int) -> int:
        level = 0
        for t in thresholds[ch]:
            if value > t:
                level += 1
        return level

    def levels_of(i: int) -> tuple[int, int, int]:
        px = sample(i)
        return classify(px[0], 0), classify(px[1], 1), classify(px[2], 2)

    if levels_of(0) != (3, 0, 3) or levels_of(1) != (0, 3, 0):
        return None, False

    capacity = per_row * rows
    bits: list[int] = []
    cursor = HEADER_CELLS

    def read_bits(count: int) -> int | None:
        nonlocal cursor
        while len(bits) < count:
            if cursor >= capacity:
                return None
            r, g, b = levels_of(cursor)
            cursor += 1
            bits.extend((r >> 1, r & 1, g >> 1, g & 1, b >> 1, b & 1))
        value = 0
        for bit in bits[:count]:
            value = (value << 1) | bit
        del bits[:count]
        return value

    version = read_bits(4)
    seq = read_bits(16)
    length = read_bits(12)
    crc = read_bits(16)
    if None in (version, seq, length, crc) or version != VERSION:
        return None, True
    payload = bytearray()
    for _ in range(length):
        byte = read_bits(8)
        if byte is None:
            return None, True
        payload.append(byte)
    if crc16(bytes((seq >> 8, seq & 0xFF)) + bytes(payload)) != crc:
        return None, True
    return Frame(seq=seq, payload=bytes(payload), cell=cell), True


@dataclass(frozen=True)
class Line:
    kind: str
    sender: str
    race: str
    sex: str      # "2" male, "3" female, else unknown
    cls: str
    channel: str
    text: str
    rate: int = 100   # reading speed, percent
    voice: str = ""   # "f5" or "sapi" as chosen in the addon; "" leaves it to config.json
    off: str | None = None   # Windows voices switched off in the addon, "|"-separated (control lines)
    sapi_voice: str = ""     # a test line for one Windows voice
    declension: bool = True  # decline the dictionary's replacements after prepositions
    options: dict = field(default_factory=dict)   # all the line's options, as sent
    raw: str = ""            # the line as typed in chat, before any rule (for the log)
    volume: int | None = None  # the addon's volume slider, percent 0..200; None: config.json alone

    def gain(self, config: dict) -> float:
        """The loudness to play this line at (0..1): config.json's `volume` times the addon's."""
        return config["volume"] / 100 * ((100 if self.volume is None else self.volume) / 100)


def parse(payload: bytes) -> Line | None:
    """kind, sender, race, sex, class, channel, options ("key=value;..."), text[, raw]. The addon
    strips the separator from the text, so a line of 7 fields has no options (defaults)."""
    fields = payload.decode("utf-8", "replace").split("\x1f")
    if len(fields) < 7:
        return None
    kind, sender, race, sex, cls, channel = fields[:6]
    options: dict[str, str] = {}
    if len(fields) >= 8:            # the addon strips \x1f from text: 8 fields always carry options
        options = dict(part.split("=", 1) for part in fields[6].split(";") if "=" in part)
        if options.get("raw") == "1" and len(fields) >= 9:
            text, raw = fields[7], "\x1f".join(fields[8:])
        else:
            text, raw = "\x1f".join(fields[7:]), ""
    else:
        text, raw = "\x1f".join(fields[6:]), ""
    rate = int(options["rate"]) if options.get("rate", "").isdigit() else 100
    volume = max(0, min(200, int(options["vol"]))) if options.get("vol", "").isdigit() else None
    return Line(kind, sender, race, sex, cls, channel, text.strip(), max(50, min(200, rate)),
                options.get("voice", ""), options.get("off"), options.get("sapi", ""),
                options.get("decl", "1") != "0", options, raw.strip(), volume)
