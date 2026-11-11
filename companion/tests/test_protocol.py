"""Round trip: the addon's Lua encoder (run with LuaJIT) -> rendered strip -> Python decoder."""
import random
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "companion"))

from wcv.protocol import Image, decode, parse  # noqa: E402

PROTOCOL = ROOT / "addon" / "WowChatVoice" / "Protocol.lua"
ENCODE = Path(__file__).with_name("encode.lua")
LEVELS = (0, 12, 24, 36)   # the addon's P.LEVELS
LUAJIT = shutil.which("luajit")


def encode(seq: int, payload: bytes, cells: int) -> list[tuple[int, int, int]]:
    out = subprocess.run([LUAJIT, str(ENCODE), str(PROTOCOL), str(seq), str(cells)],
                         input=payload, capture_output=True, check=True).stdout.decode()
    return [tuple(int(v) for v in line.split()) for line in out.splitlines()]


def render(cells, width: int, cell: int, rows: int, distort=lambda v: v, noise=0, seed=1,
           from_right: bool = False) -> Image:
    """The strip as the screen shows it: black bar, cells painted, through `distort` and noise."""
    rnd = random.Random(seed)
    height = cell * rows
    per_row = width // cell
    px = [[(0, 0, 0)] * width for _ in range(height)]
    for i, c in enumerate(cells):
        row, col = divmod(i, per_row)
        colour = tuple(LEVELS[v] for v in c)
        for dy in range(cell):
            for dx in range(cell):
                x = col * cell + dx
                if from_right:
                    x = width - 1 - x
                px[row * cell + dy][x] = colour
    raw = bytearray()
    for line in px:
        for r, g, b in line:
            def f(v):
                return max(0, min(255, round(distort(v)) + rnd.randint(-noise, noise)))
            raw += bytes((f(b), f(g), f(r), 255))
    return Image(bytes(raw), width, height)


@unittest.skipUnless(LUAJIT, "luajit not installed")
class RoundTrip(unittest.TestCase):
    PAYLOAD = "\x1f".join(["party", "Громмаш-Степи", "Orc", "2", "WARRIOR", "",
                           "Всем привет! Кто идёт в Мёртвые копи? |pipe| ё"]).encode()

    def test_plain(self):
        img = render(encode(4242, self.PAYLOAD, 1180), 2360, 2, 1)
        frame = decode(img)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.seq, 4242)
        self.assertEqual(frame.payload, self.PAYLOAD)
        line = parse(frame.payload)
        self.assertEqual(line.sender, "Громмаш-Степи")
        self.assertEqual(line.sex, "2")
        self.assertTrue(line.text.startswith("Всем привет"))

    def test_gamma_noise_and_cell_sizes(self):
        for cell in (1, 2, 3, 4):
            width = 1920
            gamma = lambda v: 255 * (v / 255) ** 0.7  # brightened, as a gamma setting would
            img = render(encode(7, self.PAYLOAD, width // cell), width, cell, 1, gamma, noise=2, seed=cell)
            frame = decode(img)
            self.assertIsNotNone(frame, f"cell {cell}")
            self.assertEqual(frame.payload, self.PAYLOAD)
            self.assertEqual(frame.cell, cell)

    def test_from_the_right_edge(self):
        for width, cell in ((2360, 2), (1921, 2), (1920, 3)):   # odd widths too: a part cell at the left
            img = render(encode(77, self.PAYLOAD, width // cell), width, cell, 1, from_right=True)
            frame = decode(img)
            self.assertIsNotNone(frame, f"{width}/{cell}")
            self.assertEqual(frame.payload, self.PAYLOAD)

    def test_darker_gamma(self):
        # a darker gamma setting squeezes the dark levels together; they must stay apart
        for gamma in (1.1, 1.2):
            img = render(encode(11, self.PAYLOAD, 960), 1920, 2, 1,
                         lambda v, g=gamma: 255 * (v / 255) ** g, noise=1, seed=7)
            frame = decode(img)
            self.assertIsNotNone(frame, f"gamma {gamma}")
            self.assertEqual(frame.payload, self.PAYLOAD)

    def test_two_rows(self):
        long = ("Ж" * 900).encode()
        cells = 2 * (1000 // 2)
        img = render(encode(1, long, cells), 1000, 2, 2)
        frame = decode(img)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.payload, long[: len(frame.payload)])
        self.assertGreater(len(frame.payload), 500)
        frame.payload.decode("utf-8")  # trimmed on a character boundary

    def test_trim_fits_one_row(self):
        long = ("Ж" * 900).encode()
        img = render(encode(9, long, 600), 1200, 2, 1)
        frame = decode(img)
        self.assertIsNotNone(frame)
        frame.payload.decode("utf-8")

    def test_empty_payload(self):
        frame = decode(render(encode(65535, b"", 960), 1920, 2, 1))
        self.assertEqual((frame.seq, frame.payload), (65535, b""))

    def test_no_strip(self):
        self.assertIsNone(decode(Image(bytes(1920 * 4 * 2), 1920, 2)))
        scene = bytes(random.Random(3).randrange(256) for _ in range(1920 * 4 * 2))
        self.assertIsNone(decode(Image(scene, 1920, 2)))

    def test_damaged(self):
        from wcv import protocol
        cells = encode(5, self.PAYLOAD, 960)
        r, g, b = cells[40]
        cells[40] = ((r + 1) % 4, g, b)
        self.assertIsNone(decode(render(cells, 1920, 2, 1)))
        self.assertEqual(protocol.last_failure, "damaged")
        decode(Image(bytes(1920 * 4 * 2), 1920, 2))
        self.assertEqual(protocol.last_failure, "absent")

    def test_covered_from_the_right(self):
        # a minimap at the top edge: the strip drawn from the right, cells 19+ covered by the scene
        from wcv import protocol
        img = render(encode(8, self.PAYLOAD, 960), 1920, 2, 1, from_right=True)
        raw = bytearray(img.raw)
        for y in range(2):
            for x in range(1673, 1882):
                i = (y * 1920 + x) * 4
                raw[i:i + 3] = bytes((60, 20, 1))
        self.assertIsNone(decode(Image(bytes(raw), 1920, 2)))
        self.assertEqual(protocol.last_failure, "damaged")


if __name__ == "__main__":
    unittest.main()
