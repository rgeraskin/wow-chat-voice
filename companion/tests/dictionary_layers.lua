-- The dictionary's layers (Dictionary.lua): the default plus the player's edits.
-- Run: mise run test-lua (from addon/WowChatVoice, it loadfiles the addon by relative path)
local ns = { db = {} }
assert(loadfile("Protocol.lua"))("WowChatVoice", ns)
assert(loadfile("Dictionary.lua"))("WowChatVoice", ns)
local D = ns.Dictionary
local function has(text, s) return text:find(s, 1, true) ~= nil end
local function count(text, s)
    local n, i = 0, 1
    while true do
        local a, b = text:find(s, i, true)
        if not a then return n end
        n, i = n + 1, b + 1
    end
end
local function empty(e) return next(e.lines) == nil and next(e.removed) == nil and e.header == nil end
local GOLD = "~\\b(\\d+)\\s*(?:з|g)\\b=\\1 [золотой|золотых|золотых]"
local GOLD_KEY = "~\\b(\\d+)\\s*(?:з|g)\\b"

-- keys
assert(D.KeyOf("Лок = чернокнижник") == "лок")
assert(D.KeyOf("хардкор*=хардк+ор*") == "хардкор*")
assert(D.KeyOf(GOLD) == GOLD_KEY, D.KeyOf(GOLD))
assert(D.KeyOf("~(?<=через )(\\d+)\\s*с\\b=\\1 сек") == "~(?<=через )(\\d+)\\s*с\\b", "a regex with '=' inside")
assert(D.KeyOf("# комментарий") == nil and D.KeyOf("просто текст") == nil)

-- no edits yet: the default; saving it unchanged stores nothing
D.Migrate(ns.db)
assert(empty(ns.db.dictionaryEdits))
local fresh = D.Text()
assert(has(fresh, "кд=кулд+аун") and has(fresh, GOLD))
D.SetText(fresh)
assert(empty(ns.db.dictionaryEdits), "unchanged text: no edits")
assert(D.Text() == fresh, "stable")
assert(has(ns.db.regexes, GOLD) and not has(ns.db.regexes, "кд="), "regexes for the companion")

-- the player deletes, changes, changes a regex's reading, adds
local mine = fresh:gsub("\nимба=имб%+а", ""):gsub("\nлок=чернокнижник", "\nлок=лок")
mine = mine:gsub((GOLD:gsub("%p", "%%%0")), ((GOLD_KEY .. "=\\1 голды"):gsub("%%", "%%%%"))) .. "абв=где\n"
D.SetText(mine)
local e = ns.db.dictionaryEdits
assert(e.removed["имба"] and e.lines["лок"] == "лок=лок" and e.lines["абв"] == "абв=где", "edits")
assert(e.lines[GOLD_KEY] and has(e.lines[GOLD_KEY], "голды"), "regex reading changed: same key")
assert(not e.removed[GOLD_KEY], "not a delete")
assert(count(D.Text(), GOLD_KEY .. "=") == 1, "one gold rule")

-- a new default: changed entries, a new one, the player's edits kept, deletes kept
local saved = D.DEFAULT
D.DEFAULT = D.DEFAULT:gsub("\nкд=кулд%+аун", "\nкд=откат"):gsub("\nлок=чернокнижник", "\nлок=варлок")
    :gsub("\nимба=имб%+а", "\nимба=очень сильно") .. "новое=слово\n"
D.Invalidate()
local now = D.Text()
assert(has(now, "кд=откат"), "untouched entry follows the default")
assert(has(now, "лок=лок") and not has(now, "лок=варлок"), "edited entry wins")
assert(not has(now, "имба="), "deleted entry stays deleted")
assert(has(now, "новое=слово") and has(now, "абв=где"), "new default entry, own entry")
assert(count(now, GOLD_KEY .. "=") == 1, "still one gold rule")
D.DEFAULT = saved
D.Invalidate()

-- a renamed default regex: whoever edited the old one does not get the new one beside it
D.RENAMED[GOLD_KEY] = "~\\b(\\d+)\\s*(?:з|g|gold)\\b"
D.DEFAULT = D.DEFAULT:gsub((GOLD:gsub("%p", "%%%0")), "~\\b(\\d+)\\s*(?:з|g|gold)\\b=\\1 [золотой|золотых|золотых]")
D.Invalidate()
D.Migrate(ns.db)
assert(not has(D.Text(), "(?:з|g|gold)"), "the new gold rule not added beside the edited old one")
assert(has(D.Text(), "голды"), "the player's own kept")
D.RENAMED = {}
D.DEFAULT = saved
D.Invalidate()

print("dictionary layers ok")
