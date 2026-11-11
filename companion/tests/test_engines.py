"""The engine manager with a fake F5: loaded on demand, notices, unloaded, falls back on error."""
import sys
import threading
import types
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wcv.protocol import Line  # noqa: E402


class FakeF5:
    fail = None

    def __init__(self, *a):
        self.ready = threading.Event()
        self.error = None
        self.stopped = False

    def start(self):
        self.error = FakeF5.fail
        if FakeF5.fail:
            self.ready.set()

    def shutdown(self):
        self.stopped = True


class FakeSapi:
    def __init__(self):
        self.said = []

    def say(self, line):
        self.said.append(line.text)


from wcv.engines import Engines  # noqa: E402

FAKE_F5 = types.SimpleNamespace(F5Speaker=FakeF5)


def wait(engines):
    for t in threading.enumerate():
        if t.name == "f5-wait":
            t.join(2)


class EnginesTest(unittest.TestCase):
    def setUp(self):
        # the engine imports F5Speaker when it loads; a fake one only for these tests
        patcher = unittest.mock.patch.dict(sys.modules, {"wcv.f5engine": FAKE_F5})
        patcher.start()
        self.addCleanup(patcher.stop)

    def make(self):
        self.sapi = FakeSapi()
        return Engines({"engine": "f5", "spoken_notices": True}, lambda *a: None, Path("."), self.sapi, None)

    def test_load_on_demand_then_unload(self):
        FakeF5.fail = None
        e = self.make()
        line = Line("say", "Орк", "Orc", "2", "", "", "текст", 100, "f5")
        self.assertIs(e.for_line(line), self.sapi)          # still loading: Windows voices meanwhile
        e.f5.ready.set()
        wait(e)
        self.assertIn("Голоса рас готовы.", self.sapi.said)
        self.assertIsInstance(e.for_line(line), FakeF5)
        f5 = e.f5
        e.want("sapi")
        self.assertTrue(f5.stopped)
        self.assertIsNone(e.f5)
        self.assertIn("Голоса рас выгружены.", self.sapi.said)
        sapi_line = Line("say", "Орк", "Orc", "2", "", "", "текст", 100, "sapi")
        self.assertIs(e.for_line(sapi_line), self.sapi)

    def test_failure_falls_back(self):
        FakeF5.fail = "нет CUDA"
        e = self.make()
        e.want("f5")
        wait(e)
        self.assertIsNone(e.f5)
        self.assertIn("Голоса рас недоступны, читаю голосами Windows.", self.sapi.said)


if __name__ == "__main__":
    unittest.main()
