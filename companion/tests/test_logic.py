"""Text, voice assignment and payload parsing (no Windows, no GPU)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wcv.assign import Assigner  # noqa: E402
from wcv.dictionary import parse as parse_rules, unescape  # noqa: E402
from wcv.catquest import Slot  # noqa: E402
from wcv.protocol import parse  # noqa: E402
from wcv.speech import sapi_rate  # noqa: E402
from wcv.text import apply_stress, merge_marks  # noqa: E402


class Text(unittest.TestCase):
    def test_dictionary_marks_win(self):
        original = "Нужен дам+агер в Мёртвые копи"
        accented = "Н+ужен дамаг+ер в М+ёртвые к+опи"   # RUAccent's guess for the slang word
        self.assertEqual(merge_marks(original, accented), "Н+ужен дам+агер в М+ёртвые к+опи")

    def test_misaligned_keeps_original(self):
        self.assertEqual(merge_marks("один два", "од+ин"), "один два")

    def test_stress_modes(self):
        self.assertEqual(apply_stress("дам+агер", "acute"), "дама́гер")
        self.assertEqual(apply_stress("дам+агер", "strip"), "дамагер")
        self.assertEqual(apply_stress("дам+агер", "plus"), "дам+агер")

    def test_sapi_rate(self):
        self.assertEqual(sapi_rate(0, 100), 0)
        self.assertEqual(sapi_rate(0, 300), 10)
        self.assertLess(sapi_rate(0, 50), 0)
        self.assertEqual(sapi_rate(5, 300), 10)


def slots():
    out = []
    for base in ("orc-male", "orc-male#60"):
        for shift in (0.0, -1.5, 1.5):
            sid = base if shift == 0 else f"{base}^{shift:+g}"
            out.append(Slot(sid, base, "orc", "male", shift, f"{sid}.wav", "текст"))
    out.append(Slot("human-female", "human-female", "human", "female", 0.0, "hf.wav", "текст"))
    out.append(Slot("human-male", "human-male", "human", "male", 0.0, "hm.wav", "текст"))
    out.append(Slot("creature/saurfang", "creature/saurfang", "", "", 0.0, "s.wav", "текст"))
    return out


class Assign(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "a.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_orcs_differ_and_base_voices_first(self):
        a = Assigner(slots(), self.path)
        got = [a.slot_for(f"Орк{i}", "Orc", "2", now=1000 + i).id for i in range(6)]
        self.assertEqual(len(set(got)), 6, got)
        self.assertEqual({g for g in got[:2]}, {"orc-male", "orc-male#60"})

    def test_stable_and_persisted(self):
        a = Assigner(slots(), self.path)
        first = a.slot_for("Громмаш-Степи", "Orc", "2", now=1).id
        self.assertEqual(a.slot_for("Громмаш-Степи", "Orc", "2", now=2).id, first)
        b = Assigner(slots(), self.path)
        self.assertEqual(b.slot_for("Громмаш-Степи", "Orc", "2", now=3).id, first)

    def test_unknown_race_and_sex(self):
        a = Assigner(slots(), self.path)
        self.assertEqual(a.slot_for("Волчок", "Worgen", "3").id, "human-female")
        self.assertEqual(a.slot_for("Кто-то", "", "").race, "human")

    def test_override(self):
        a = Assigner(slots(), self.path, {"Тралл": "creature/saurfang"})
        self.assertEqual(a.slot_for("Тралл-Степи", "Orc", "2").id, "creature/saurfang")


class Regexes(unittest.TestCase):
    SAVED = r'WTS=продам\n~(\\d+)\\s*кк\\b=\\g<1>000000\n~(\\d+)\\s*к\\b=\\g<1>000\n~[=битая\n~(?=x)y=z'

    def test_saved_variables_round_trip(self):
        text = unescape(self.SAVED)
        self.assertIn("~(\\d+)\\s*к\\b=\\g<1>000", text)
        errors = []
        rules = parse_rules(text, errors.append)
        self.assertEqual(len(rules), 3)          # the broken one is reported and skipped
        self.assertEqual(len(errors), 1)
        out = "продам за 5к, а меч за 2 КК"
        for pattern, replacement in rules:
            out = pattern.sub(replacement, out)
        self.assertEqual(out, "продам за 5000, а меч за 2000000")

    def test_lookahead_split_at_last_equals(self):
        rules = parse_rules("~a(?=b)=c", print)
        self.assertEqual(rules[0][0].sub(rules[0][1], "ab"), "cb")


class Payload(unittest.TestCase):
    def test_options(self):
        line = parse("\x1f".join(["say", "Имя", "Orc", "2", "WARRIOR", "", "rate=120;voice=sapi", "a=b текст"]).encode())
        self.assertEqual((line.rate, line.voice, line.text), (120, "sapi", "a=b текст"))

    def test_text_with_equals_is_not_options(self):
        line = parse("\x1f".join(["say", "Имя", "Orc", "2", "WARRIOR", "", "x = 5"]).encode())
        self.assertEqual((line.rate, line.voice, line.text), (100, "", "x = 5"))

    def test_voice_names_with_spaces(self):
        name = "Microsoft Irina Desktop - Russian"
        line = parse("\x1f".join(["test", "Проверка", "", "", "", "", f"rate=100;voice=sapi;sapi={name}",
                                    "Привет!"]).encode())
        self.assertEqual((line.voice, line.sapi_voice, line.text), ("sapi", name, "Привет!"))

    def test_declension_option(self):
        on = parse("\x1f".join(["say", "И", "", "", "", "", "rate=100;voice=f5;decl=1", "т"]).encode())
        off = parse("\x1f".join(["say", "И", "", "", "", "", "rate=100;voice=f5;decl=0", "т"]).encode())
        bare = parse("\x1f".join(["say", "И", "", "", "", "", "rate=100;voice=f5", "т"]).encode())
        self.assertEqual((on.declension, off.declension, bare.declension), (True, False, True))

    def test_without_options(self):
        line = parse("\x1f".join(["say", "Имя", "Orc", "2", "WARRIOR", "", "150 золота"]).encode())
        self.assertEqual((line.rate, line.text), (100, "150 золота"))


if __name__ == "__main__":
    unittest.main()


class VoiceListFile(unittest.TestCase):
    def test_render(self):
        from wcv.voicelist import label, render

        class V:
            def __init__(self, d, e, g):
                self.description, self.engine, self.gender = d, e, g
        voices = [V("Microsoft Svetlana Online (Natural) - Russian (Russia)", "edge", "Female"),
                  V("Aidar (Russian)", "silero", "Male"), V("Anna", "rhvoice", "Female"),
                  V('Microsoft Irina Desktop - Russian', "other", "Female")]
        self.assertEqual([label(v) for v in voices],
                         ["Svetlana (Edge)", "Aidar (Silero)", "Anna (RHVoice)", "Irina Desktop (Windows)"])
        text = render(voices, lambda v: "Irina" in v.description)
        self.assertIn('{ name = "Anna", label = "Anna (RHVoice)", gender = "Female", on = true },', text)
        self.assertIn('label = "Irina Desktop (Windows)", gender = "Female", on = false', text)


class Plurals(unittest.TestCase):
    def test_russian_forms(self):
        from wcv.dictionary import plurals
        forms = "[дамагер|дамагера|дамагеров]"
        got = {n: plurals(f"{n} {forms}") for n in (0, 1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 101, 111)}
        self.assertEqual(got[1], "1 дамагер")
        self.assertEqual(got[21], "21 дамагер")
        self.assertEqual(got[101], "101 дамагер")
        self.assertEqual(got[2], "2 дамагера")
        self.assertEqual(got[22], "22 дамагера")
        for n in (0, 5, 11, 12, 14, 25, 111):
            self.assertEqual(got[n], f"{n} дамагеров")
        self.assertEqual(plurals("текст [a|b] без числа"), "текст [a|b] без числа")


class StableVoices(unittest.TestCase):
    def test_switching_a_voice_off_moves_only_its_people(self):
        from wcv.speech import Speaker, Voice
        sp = Speaker({"players": {}, "exclude": [], "gender_overrides": {}}, print)
        voices = [Voice(None, f"Voice{i}", "Male", "rhvoice") for i in range(12)]
        sp.all_voices = voices
        sp.set_disabled(set())
        names = [f"Игрок{i}" for i in range(200)]
        before = {n: sp.voice_for(n, "2").description for n in names}
        sp.set_disabled({"Voice3"})
        after = {n: sp.voice_for(n, "2").description for n in names}
        moved = [n for n in names if before[n] != after[n]]
        self.assertTrue(moved)
        self.assertTrue(all(before[n] == "Voice3" for n in moved), "only Voice3's people may move")
        self.assertGreater(len(set(before.values())), 8)      # still spread over the voices


class ResetAssignments(unittest.TestCase):
    def test_reset_forgets(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.json"
            a = Assigner(slots(), path)
            a.slot_for("Орк1", "Orc", "2", now=1)
            a.reset()
            self.assertEqual(Assigner(slots(), path).known, {})


class RegexOverStrip(unittest.TestCase):
    def test_parts_assembled_once_complete(self):
        from wcv.dictionary import Regexes
        r = Regexes({}, lambda *a: None)
        r.receive({"id": "ab12", "part": "2", "of": "2"}, "~(\\d+)\\s*к\\b=\\g<1>000")
        self.assertEqual(r.rules, [])                      # part 1 still missing
        r.receive({"id": "ab12", "part": "1", "of": "2"}, "~го+=го")
        self.assertEqual(len(r.rules), 2)
        self.assertEqual(r.apply("гоооо за 5к"), "го за 5000")
        r.refresh()                                         # the saved variables are no longer read
        self.assertEqual(r.from_addon, "ab12")

    def test_saved_variables(self):
        # without the game: the merged regexes the addon keeps in its saved variables
        import tempfile
        from wcv.dictionary import Regexes
        text = ('WowChatVoiceDB = {\n["dictionaryEdits"] = {["lines"] = {["лок"] = "лок=лок"}},\n'
                '["regexes"] = "~(\\\\d+)\\\\s*к\\\\b=\\\\g<1>000\\n~го+=го",\n}\n')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "WowChatVoice.lua"
            path.write_text(text, encoding="utf-8")
            r = Regexes({}, lambda *a: None)
            r.path = path
            r.refresh()
            self.assertEqual(len(r.rules), 2)
        self.assertEqual(r.apply("гооо за 5к"), "го за 5000")

    def test_empty_set(self):
        from wcv.dictionary import Regexes
        r = Regexes({}, lambda *a: None)
        r.receive({"id": "0001", "part": "1", "of": "1"}, "-")
        self.assertEqual((r.rules, r.from_addon), ([], "0001"))


class PlayerStop(unittest.TestCase):
    def test_stop_drops_queued_and_late_lines(self):
        from wcv.audio import Player, wav
        p = Player()
        data = wav(b"\0\0" * 100, 22050)
        made_before_stop = p.generation
        p.play(data)
        p.play(data)
        p.stop()
        self.assertTrue(p.items.empty())
        p.play(data, made_before_stop)            # finished synthesising after the stop: dropped
        self.assertTrue(p.items.empty())
        p.play(data, p.generation)
        self.assertEqual(p.items.qsize(), 1)

    def test_sentence_groups(self):
        from wcv.f5engine import sentence_groups
        self.assertEqual(sentence_groups("Привет. Кто идёт? Собираемся у входа."),
                         ["Привет.", "Кто идёт?", "Собираемся у входа."])
        self.assertEqual(sentence_groups("Кто в ОП? Нужен танк?"), ["Кто в ОП?", "Нужен танк?"])
        self.assertEqual(sentence_groups("Привет. Всем. Идёшь?"), ["Привет. Всем.", "Идёшь?"])


class RawText(unittest.TestCase):
    def test_raw_after_text(self):
        line = parse("\x1f".join(["party", "И", "", "", "", "", "rate=100;voice=f5;decl=1;raw=1",
                                    "продам дам+агер", "WTS дд"]).encode())
        self.assertEqual((line.text, line.raw), ("продам дам+агер", "WTS дд"))

    def test_without_raw_flag(self):
        line = parse("\x1f".join(["party", "И", "", "", "", "", "rate=100;voice=f5", "текст"]).encode())
        self.assertEqual((line.text, line.raw), ("текст", ""))

    def test_raw_cut_off_by_the_strip(self):
        # the strip trims the payload's end: the raw text may lose its tail, or be missing entirely
        line = parse("\x1f".join(["party", "И", "", "", "", "", "raw=1", "текст"]).encode())
        self.assertEqual((line.text, line.raw), ("текст", ""))


class RefCheck(unittest.TestCase):
    def test_similarity(self):
        from wcv.refcheck import similarity
        text = "Возвращайся ко мне, когда соберёшь достаточно мази."
        self.assertEqual(similarity(text, "возвращайся ко мне когда соберешь достаточно мази"), 1.0)
        leaked = "нести в сердце горе. Возвращайся ко мне, когда соберёшь достаточно мази."
        self.assertLess(similarity(text, leaked), 0.85)


class BankCache(unittest.TestCase):
    def test_checked_bank_is_reused_and_never_downgraded(self):
        import json
        import tempfile
        from wcv import catquest
        with tempfile.TemporaryDirectory() as d:
            pack, out = Path(d) / "pack", Path(d) / "voices"
            pack.mkdir(); out.mkdir()
            (pack / "Index.lua").write_text("x", encoding="utf-8")
            stamp = {"version": catquest.BANK_VERSION, "pack": str(pack), "index_size": 1, "shifts": [], "checked": True}
            (out / "bank.json").write_text(json.dumps({"stamp": stamp, "slots": []}), encoding="utf-8")
            made = []
            self.assertEqual(catquest.build(pack, out, [], print, lambda: made.append(1)), [])
            self.assertEqual(catquest.build(pack, out, [], print, None), [])
            self.assertEqual(made, [])                       # no Whisper for a bank already checked


class Questions(unittest.TestCase):
    def test_kind(self):
        from wcv.intonation import kind, question_word, stressed_vowel
        self.assertEqual(kind("Кт+о идёт?"), "wh")
        self.assertEqual(kind("Ну а где т+анк?"), "wh")
        self.assertEqual(question_word("Ну а где т+анк?"), 2)
        self.assertEqual(kind("Идёшь с н+ами?"), "yes_no")
        self.assertIsNone(kind("Идём."))
        self.assertEqual(kind("Кт+о-нибудь прода+ёт с+умки?"), "yes_no")
        self.assertEqual(kind("Ну кто-то идёт?"), "yes_no")
        self.assertEqual(stressed_vowel("Ск+олько ст+оит?", 0), (0, 4))
        self.assertEqual(stressed_vowel("Почем+у т+ы?", 0), (2, 4))
        self.assertEqual(stressed_vowel("Ну где?", 1), (1, 2))

    def test_yes_no(self):
        from wcv.intonation import is_yes_no
        self.assertTrue(is_yes_no("Идёшь с нами в Мёртвые к+опи?"))
        self.assertTrue(is_yes_no("Привет. Готов ли ты?"))
        self.assertFalse(is_yes_no("Кто идёт с нами?"))
        self.assertFalse(is_yes_no("Как дела?"))
        self.assertFalse(is_yes_no("Идём в копи."))


class Volume(unittest.TestCase):
    def test_volume_option(self):
        from wcv.protocol import parse
        line = parse("say\x1fВася\x1fOrc\x1f2\x1fWARRIOR\x1f\x1frate=100;vol=40;voice=f5\x1fпривет".encode())
        self.assertEqual(line.volume, 40)
        self.assertAlmostEqual(line.gain({"volume": 50}), 0.2)
        bare = parse("say\x1fВася\x1fOrc\x1f2\x1fWARRIOR\x1f\x1frate=100;voice=f5\x1fпривет".encode())
        self.assertIsNone(bare.volume)
        self.assertAlmostEqual(bare.gain({"volume": 100}), 1.0)


class Limiter(unittest.TestCase):
    def test_soft_limit(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy")
        from wcv.f5engine import limit
        x = np.array([0.1, -0.5, 0.79, 1.2, -1.9, 3.0], dtype="float32")
        y = limit(x)
        self.assertTrue(np.allclose(y[:3], x[:3]))              # below the knee: untouched
        self.assertTrue(np.all(np.abs(y) <= 1.0))               # never past full scale
        self.assertTrue(abs(y[3]) < abs(y[5]))                  # louder stays louder


class NumberAgreement(unittest.TestCase):
    def setUp(self):
        try:
            import num2words  # noqa: F401
            import pymorphy3  # noqa: F401
        except ImportError:
            self.skipTest("num2words / pymorphy3")

    def test_agree(self):
        from wcv.text import numbers_to_words as f
        cases = {
            "на 1 р+уку": "на одну р+уку", "без 1 руки": "без одной руки", "2 руки": "две руки",
            "на 1 мага": "на одного мага", "нужен 1 маг": "нужен один маг", "1 золотой": "один золотой",
            "по 1 золотому": "по одному золотому", "с 5 магами": "с пятью магами", "в 3 сумках": "в трёх сумках",
            "21 сумка": "двадцать одна сумка", "с 21 магом": "с двадцатью одним магом",
            "11 рук": "одиннадцать рук", "12 рук": "двенадцать рук", "22 руки": "двадцать две руки",
            "2 дамагера": "два дамагера",   # slang, unknown to pymorphy: left alone
            "за 2 часа": "за два часа", "1 hp": "один hp", "1.": "один.",
        }
        for text, spoken in cases.items():
            self.assertEqual(f(text), spoken, text)

    def test_silver_rule(self):
        from wcv.dictionary import parse, plurals
        from wcv.text import numbers_to_words
        rules = parse(r"~(?<!через )\b(\d+)\s*(?:с|s)\b(?!\s*(?:кд|cd))=\1 [серебро|серебра|серебра]", print)
        def say(text):
            for pattern, replacement in rules:
                text = pattern.sub(replacement, text)
            return numbers_to_words(plurals(text))
        self.assertEqual(say("продам за 1с"), "продам за одно серебро")
        self.assertEqual(say("2с"), "два серебра")
        self.assertEqual(say("15с"), "пятнадцать серебра")
        self.assertNotIn("серебр", say("через 5с кд"))   # seconds of a cooldown, not money

    def test_seconds_rules(self):
        from wcv.dictionary import parse, plurals
        from wcv.text import numbers_to_words
        rules = parse("\n".join([
            r"~(?<!через )\b(\d+)\s*(?:с|s)\b(?!\s*(?:кд|cd|кулд\+?аун))=\1 [серебро|серебра|серебра]",
            r"~(?<=через )(\d+)\s*(?:с|s|сек)\b=\1 [секунду|секунды|секунд]",
            r"~\b(\d+)\s*(?:с|s|сек)\b(?=\s*(?:кд|cd|кулд\+?аун)\b)=\1 [секунда|секунды|секунд]",
        ]), print)
        def say(text):
            for pattern, replacement in rules:
                text = pattern.sub(replacement, text)
            return numbers_to_words(plurals(text))
        cases = {
            "через 1с": "через одну секунду", "через 5с пул": "через пять секунд пул",
            "через 30 сек": "через тридцать секунд", "Через 2s": "Через две секунды",
            "1с кд": "одна секунда кд", "5с кд": "пять секунд кд", "10 сек cd": "десять секунд cd",
            # as it really comes: the addon has made "кд" "кулд+аун" before the regexes run
            "5с кулд+аун": "пять секунд кулд+аун", "1с кулд+аун": "одна секунда кулд+аун",
            "продам за 5с": "продам за пять серебра", "1с": "одно серебро",
        }
        for text, spoken in cases.items():
            self.assertEqual(say(text), spoken, text)
