"""Declension of the addon's dictionary replacements after a preposition ("в ОП" -> "в Огненную
пропасть", "для дд" -> "для дамагера"), with pymorphy3.

The addon marks each replacement as \\x02...\\x03. The case comes from the word before it; only the
start of the replacement is declined - adjectives and the first noun - so a name's genitive tail
stays ("Глубины Чёрной горы" -> "в Глубины Чёрной горы").
"""
from __future__ import annotations

import re
import threading

MARKED = re.compile(r"\x02([^\x02\x03]*)\x03")
PREVIOUS = re.compile(r"([а-яё]+)\W*$", re.IGNORECASE)
WORD = re.compile(r"[\w'+]+|[^\w'+]+")

# Preposition -> case. "в"/"на" can be "where" (prepositional) as well as "where to" (accusative);
# chat looking for groups means "where to" far more often.
CASES = {
    "в": "accs", "во": "accs", "на": "accs", "за": "accs", "через": "accs", "про": "accs",
    "из": "gent", "изо": "gent", "у": "gent", "до": "gent", "для": "gent", "после": "gent", "от": "gent",
    "без": "gent", "возле": "gent", "около": "gent", "кроме": "gent", "вместо": "gent", "из-за": "gent",
    "к": "datv", "ко": "datv", "по": "datv",
    "с": "ablt", "со": "ablt", "под": "ablt", "над": "ablt", "перед": "ablt", "между": "ablt",
    "о": "loct", "об": "loct", "при": "loct",
}
DECLINABLE = {"ADJF", "PRTF", "NOUN"}
CONJUNCTIONS = {"и", "или", "либо", "да"}   # "с танком и чернокнижником": the case carries over


def strip_marks(text: str) -> str:
    return text.replace("\x02", "").replace("\x03", "")


class Inflector:
    def __init__(self, log, enabled: bool = True):
        self.log, self.enabled, self.morph = log, enabled, None
        self.lock = threading.Lock()

    def load(self) -> None:
        if not self.enabled or self.morph is not None:
            return
        try:
            import pymorphy3
        except ImportError:
            self.log("pymorphy3 не установлен: замены словаря не склоняются")
            self.enabled = False
            return
        self.morph = pymorphy3.MorphAnalyzer()

    def apply(self, text: str) -> str:
        """`text` with each marked replacement declined after its preposition, marks removed."""
        if "\x02" not in text:
            return text
        if not self.enabled:
            return strip_marks(text)
        with self.lock:
            self.load()
            if self.morph is None:
                return strip_marks(text)
            out, last, carried = [], 0, None
            for m in MARKED.finditer(text):
                before = text[last:m.start()]
                out.append(before)
                prev = PREVIOUS.search(strip_marks("".join(out)))
                word = prev.group(1).lower() if prev else ""
                if word in CASES:
                    case = CASES[word]
                elif word in CONJUNCTIONS and re.fullmatch(r"\s*\w+\s*", before):
                    case = carried          # "X и Y": Y takes X's case
                else:
                    case = None
                out.append(self.decline(m.group(1), case) if case else m.group(1))
                carried = case
                last = m.end()
            out.append(text[last:])
            return strip_marks("".join(out))

    def decline(self, phrase: str, case: str) -> str:
        """The start of `phrase` (adjectives up to and including the first noun) put in `case`."""
        parts = WORD.findall(phrase)
        words = [i for i, p in enumerate(parts) if re.match(r"[\w'+]", p)]
        parsed = {}
        head = None
        for n, i in enumerate(words):
            p = self._parse(parts[i], adjective_first=n + 1 < len(words))
            if p is None or p.tag.POS not in DECLINABLE:
                break
            parsed[i] = p
            if p.tag.POS == "NOUN":
                head = p
                break
        if head is None:
            return phrase
        if case == "accs" and head.tag.gender in ("masc", "neut") and head.tag.number != "plur" and \
                not self.morph.word_is_known(parts[[i for i in parsed if parsed[i] is head][0]].replace("+", "").lower()):
            return phrase       # an unknown name (Ульдаман, Зул'Фаррак) is a place: accusative = nominative
        for i, p in parsed.items():
            grammemes = {case}
            if p.tag.POS != "NOUN":
                if head.tag.number:
                    grammemes.add(head.tag.number)
                if head.tag.number == "sing" and head.tag.gender:
                    grammemes.add(head.tag.gender)
                if case == "accs" and head.tag.animacy and (head.tag.number == "plur" or head.tag.gender == "masc"):
                    grammemes.add(head.tag.animacy)
            form = p.inflect(grammemes)
            if form is not None:
                parts[i] = self._like(parts[i], form.word)
        return "".join(parts)

    def _parse(self, word: str, adjective_first: bool = False):
        """The nominative reading of `word`; an adjective one first when a word follows ("Мёртвые
        копи": pymorphy's best guess for "мёртвые" is the noun "the dead")."""
        plain = word.replace("+", "")
        if not re.search(r"[а-яё]", plain, re.IGNORECASE):
            return None
        options = self.morph.parse(plain)
        if not options:
            return None
        nominative = [o for o in options if o.tag.case == "nomn" and o.tag.POS in DECLINABLE]
        if adjective_first:
            adjectives = [o for o in nominative if o.tag.POS in ("ADJF", "PRTF")]
            if adjectives:
                return adjectives[0]
        return (nominative or options)[0]

    @staticmethod
    def _like(original: str, new: str) -> str:
        """`new` with the letter case of `original` (letter by letter, so "Зул'Фаррак" keeps its
        second capital) and its stress mark, when the stressed vowel is in the unchanged part."""
        plain = original.replace("+", "")
        new = "".join(c.upper() if i < len(plain) and plain[i].isupper() else c for i, c in enumerate(new))
        if "+" in original:
            at = original.index("+")
            common = 0
            while common < min(len(plain), len(new)) and plain[common].lower() == new[common].lower():
                common += 1
            if at < common:
                new = new[:at] + "+" + new[at:]
        return new
