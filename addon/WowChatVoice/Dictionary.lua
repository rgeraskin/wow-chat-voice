-- The slang dictionary, applied before a line goes to the strip ("WTS" is said as "продам"). One
-- entry per line, "key=replacement"; case and ё/е do not matter; "#" starts a comment. A key is a
-- word, a phrase ("мертвые копи"), or a stem ending in "*" ("дамагер*" also takes "дамагера"; a
-- "*" in the replacement gets the ending). A replacement may mark stress with "+" before the vowel
-- ("дам+агер"); the companion turns that into what each voice understands. An empty replacement
-- drops the word. A line starting with "~" is a regular expression for the companion (Python,
-- case-insensitive, split at the last "="), which reads it from the saved variables after /reload;
-- the addon leaves such lines alone.
local _, ns = ...

local D = {}
ns.Dictionary = D

D.DEFAULT = [[
# слово=как читать; ударение: + перед гласной (дам+агер)
# фразы: мертвые копи=мёртвые к+опи; склонения: дамагер*=дам+агер* (окончание переносится)
# регулярки (Python, применяет программа, после правки — /reload): ~(\d+)\s*к\b=\g<1>000
~\b(\d+)\s*(?:лвл|lvl|ур|уровень)\b=<\1> уровень
~\b(\d+)\s*(?:з|g)\b=\1 [золотой|золотых|золотых]
~\b(\d+)\s*(?:голд|г\+олд)\w*\b=\1 [золотой|золотых|золотых]
~(?<!через )\b(\d+)\s*(?:с|s)\b(?!\s*(?:кд|cd|кулд\+?аун))=\1 [серебро|серебра|серебра]
# секунды — только где понятно, что это время: «через 5с», «5с кд» (в остальных местах «5с» — серебро);
# «кд» к этому времени уже «кулдаун» (слова заменяются раньше регулярок), поэтому ждём оба
~(?<=через )(\d+)\s*(?:с|s|сек)\b=\1 [секунду|секунды|секунд]
~\b(\d+)\s*(?:с|s|сек)\b(?=\s*(?:кд|cd|кулд\+?аун)\b)=\1 [секунда|секунды|секунд]
# число и роль: 2дд = «2 дамагера»; в [ ] три формы: для 1, для 2-4, для 5 и больше; <\1> — порядковое: «60 лвл» = «шестидесятый уровень»
~\b(\d+)\s*(?:дд|дам\+агер)\b=\1 [дам+агер|дам+агера|дам+агеров]
~\b(\d+)\s*(?:рдд|дальний дам\+агер)\b=\1 [дальний дам+агер|дальних дам+агера|дальних дам+агеров]
~\b(\d+)\s*(?:мдд|ближний дам\+агер)\b=\1 [ближний дам+агер|ближних дам+агера|ближних дам+агеров]
~\b(\d+)\s*(?:хилл?|х\+ил)\b=\1 [х+ил|х+ила|х+илов]
~\b(\d+)\s*(?:танк|т\+анк)\b=\1 [т+анк|т+анка|т+анков]
~\bдд(\d{1,2})\b=дам+агер, уровень \1
~\bрдд(\d{1,2})\b=дальний дам+агер, уровень \1
~\bмдд(\d{1,2})\b=ближний дам+агер, уровень \1
~\bхилл?(\d{1,2})\b=х+ил, уровень \1
~\bтанк(\d{1,2})\b=т+анк, уровень \1
~\bварр?(\d{1,2})\b=воин, уровень \1
~\bприст(\d{1,2})\b=жрец, уровень \1
~\bшам(\d{1,2})\b=шам+ан, уровень \1
~\bхант(\d{1,2})\b=охотник, уровень \1
~\bмаг(\d{1,2})\b=маг, уровень \1
~\bрог[аи]?(\d{1,2})\b=разбойник, уровень \1
~\bлок(\d{1,2})\b=чернокнижник, уровень \1
~\bпал(\d{1,2})\b=паладин, уровень \1
~\bдру(?:ль|ид)?(\d{1,2})\b=друид, уровень \1
~(\d+)\s*кк\b=\g<1>000000
~(\d+)\s*к\b=\g<1>000
WTS=продам
WTB=куплю
WTT=обменяю
LFG=ищу группу
LFM=ищем ещё
LF=ищу
LF1M=нужен ещё один
LF2M=нужны ещё двое
LF3M=нужны ещё трое
ty=спасибо
thx=спасибо
спс=спасибо
пасиб=спасибо
pls=пожалуйста
plz=пожалуйста
плз=пожалуйста
пж=пожалуйста
пжл=пожалуйста
нзч=не за что
хз=не знаю
мб=может быть
кст=кстати
кста=кстати
оч=очень
прив=привет
пок=пока
кк=окей
ок=окей
ok=окей
gg=гуд гейм
гг=гуд гейм
afk=отошёл
афк=отошёл
brb=сейчас вернусь
oom=нет маны
оом=нет маны
кд=кулд+аун
cd=кулд+аун
хп=здоровье
дд=дам+агер
рдд=дальний дам+агер
мдд=ближний дам+агер
дамагер*=дам+агер*
хилер*=х+илер*
рл=рейд лидер
пл=лидер группы
лс=личку
тп=телепорт
нид=нужно
инст=инстанс
хил=х+ил
хилл=х+ил
хилы=х+илы
танк=т+анк
кастер=к+астер
мили=м+или
вар=воин
варр=воин
прист=жрец
шам=шам+ан
хант=охотник
хардкор*=хардк+ор*
друль=друид
дру=друид
лок=чернокнижник
варлок=чернокнижник
твинк=тв+инк
нуб=н+уб
лфг=ищу группу
лфм=ищем людей
LFR=ищу рейд
LF4M=нужны ещё четверо
пати=п+ати
ресет=рес+ет
аттюн=атт+юн
ролл=р+олл
грид=жадность
AH=аукцион
аук=аукц+ион
голд=г+олд
голды=г+олды
маунт=м+аунт
лут=л+ут
BoE=привязка при надевании
BoP=привязка при поднятии
агро=+агро
агрятся=+агрятся
агрится=+агрится
агрить=+агрить
агрит=+агрит
агрил=+агрил
агрила=+агрила
агрили=+агрили
агрю=+агрю
аггро=+агро
пул=п+ул
пулл=п+ул
пуллить=п+уллить
вайп=в+айп
кайт=к+айт
кайтить=к+айтить
сап=с+ап
сайленс=с+айленс
дебафф=деб+аф
дебаф=деб+аф
бафф=б+аф
баф=б+аф
аое=а о +е
AoE=а о +е
хот=х+от
дот=д+от
рес=р+ес
ресс=р+ес
бр=боевое воскрешение
дс=дисконн+ект
инк=инк+ам
inc=инк+ам
адд=+адд
моб=м+об
мобы=м+обы
треш=тр+эш
трэш=тр+эш
респ=р+есп
дпс=дэ пэ +эс
dps=дэ пэ +эс
фарм=ф+арм
гринд=гр+инд
ганк=г+анк
лос=линия видимости
LoS=линия видимости
лвл=уровень
lvl=уровень
лол=л+ол
lol=л+ол
ппц=писец
омг=о боже
omg=о боже
имхо=+имхо
imho=+имхо
вп=хорошо сыграно
wp=хорошо сыграно
гз=поздравляю
gz=поздравляю
grats=поздравляю
грац=поздравляю
gl=удачи
гл=удачи
ГИ=гильдия
hf=приятной игры
np=не за что
sry=извини
сори=с+ори
btw=кстати
omw=уже иду
wtf=что за чёрт
имба=имб+а
нерф=н+ерф
ОП=Огненная пропасть
RFC=Огненная пропасть
WC=Пещеры стенаний
дедмайнс=Мёртвые копи
КТК=Крепость Тёмного Клыка
SFK=Крепость Тёмного Клыка
стокады=Тюрьма Штормграда
подгород*=П+одгород*
ПВП=пэвэп+э
PvP=пэвэп+э
НП=Непроглядная пучина
BFD=Непроглядная пучина
гномер=Гномреган
RFK=Лабиринты Иглошкурых
РФК=Лабиринты Иглошкурых
RFD=Курганы Иглошкурых
РФД=Курганы Иглошкурых
СМ=Монастырь Алого ордена
SM=Монастырь Алого ордена
ульда=Ульдам+ан
ЗФ=Зул'Ф+аррак
ZF=Зул'Ф+аррак
БРД=Глубины Чёрной горы
BRD=Глубины Чёрной горы
ЛБРС=Нижняя часть Пика Чёрной горы
LBRS=Нижняя часть Пика Чёрной горы
УБРС=Верхняя часть Пика Чёрной горы
UBRS=Верхняя часть Пика Чёрной горы
страт=Стратх+ольм
strat=Стратх+ольм
шоло=Некросит+ет
некро=Некросит+ет
MC=Огненные недра
оня=Логово Ониксии
онька=Логово Ониксии
БВЛ=Логово Крыла Тьмы
BWL=Логово Крыла Тьмы
ЗГ=Зул'Гур+уб
ZG=Зул'Гур+уб
АК20=Руины Ан'Кираджа
АК40=Храм Ан'Кираджа
AQ=Ан'Кир+адж
накс=Наксрам+ас
БГ=поле боя
BG=поле боя
АВ=Альтеракская долина
AV=Альтеракская долина
АБ=Низина Арати
AB=Низина Арати
ВСГ=Ущелье Песни Войны
WSG=Ущелье Песни Войны
]]

local exact, stems, phrases = {}, {}, {}

-- Sorting: Russian keys first, then Latin, then digits and other symbols, regexes (~) last;
-- within a group alphabetically (case and ё/е ignored). Comments travel with the entry below them;
-- the comment block at the top stays the header.
local function SortKey(entry)
    if entry:sub(1, 1) == "~" then return 4, entry end
    local key = D.Norm(entry:match("^(.-)%s*=") or entry)
    local first = key:byte(1) or 0
    if first >= 0xC0 then return 1, key end
    if key:match("^%a") then return 2, key end
    return 3, key
end

function D.Sort(text)
    local header, items, pending, top = {}, {}, {}, true
    for line in ((text or "") .. "\n"):gmatch("(.-)\r?\n") do
        local trimmed = line:match("^%s*(.-)%s*$")
        if trimmed:sub(1, 1) == "#" then
            if top then header[#header + 1] = trimmed else pending[#pending + 1] = trimmed end
        elseif trimmed ~= "" then
            top = false
            local group, key = SortKey(trimmed)
            items[#items + 1] = { line = trimmed, comments = pending, group = group, key = key, order = #items }
            pending = {}
        end
    end
    table.sort(items, function(a, b)
        if a.group ~= b.group then return a.group < b.group end
        if a.key ~= b.key then return a.key < b.key end
        return a.order < b.order
    end)
    local out = {}
    for _, line in ipairs(header) do out[#out + 1] = line end
    for _, item in ipairs(items) do
        for _, c in ipairs(item.comments) do out[#out + 1] = c end
        out[#out + 1] = item.line
    end
    for _, c in ipairs(pending) do out[#out + 1] = c end
    return table.concat(out, "\n") .. "\n"
end

--- Lower case for ASCII and Russian letters, with ё as е (UTF-8; Lua's lower() knows ASCII only).
--- Byte lengths are kept, so a normalised word and the original line up byte for byte.
function D.Norm(s)
    -- ASCII by hand rather than s:lower(): byte for byte, whatever the client's lower() does with
    -- UTF-8 (/wcv diag on the ruRU Forever client: lower() handles Cyrillic correctly too).
    s = s:gsub("[A-Z]", function(c) return string.char(c:byte() + 32) end)
    s = s:gsub("\208([\144-\159])", function(c) return "\208" .. string.char(c:byte() + 32) end)
    s = s:gsub("\208([\160-\175])", function(c) return "\209" .. string.char(c:byte() - 32) end)
    s = s:gsub("\208\129", "\208\181"):gsub("\209\145", "\208\181")
    return s
end

local WORD = "[%w\128-\255]+"

local function Words(s)
    local out = {}
    for w in s:gmatch(WORD) do out[#out + 1] = D.Norm(w) end
    return out
end

--- Entries of `text`: { words = { normalised }, star = true when the last word ends in "*",
--- value = replacement }.
function D.Parse(text)
    local out = {}
    for line in (text or ""):gmatch("[^\r\n]+") do
        if not line:match("^%s*#") then
            local key, value = line:match("^%s*(.-)%s*=%s*(.-)%s*$")
            if line:match("^%s*~") then
                out[#out + 1] = { regex = line:match("^%s*(.-)%s*$"), words = {} }
            elseif key and key ~= "" then
                local star = key:sub(-1) == "*"
                local words = Words(star and key:sub(1, -2) or key)
                if #words > 0 then out[#out + 1] = { words = words, star = star, value = value } end
            end
        end
    end
    return out
end

--- The regular expression lines (the program applies them; the addon sends them over the strip).
function D.Regexes()
    local out = {}
    for _, e in ipairs(D.Parse(D.Text())) do
        if e.regex then out[#out + 1] = e.regex end
    end
    return out
end

function D.Rebuild()
    if ns.RegexesChanged then ns.RegexesChanged() end
    -- for the companion when it reads the saved variables (the game not running or not yet sent)
    ns.db.regexes = table.concat(D.Regexes(), "\n")
    exact, stems, phrases = {}, {}, {}
    for _, e in ipairs(D.Parse(D.Text())) do
        if e.regex then
            -- the companion's
        elseif #e.words == 1 and not e.star then
            exact[e.words[1]] = e.value
        elseif #e.words == 1 then
            stems[#stems + 1] = e
        else
            local first = e.words[1]
            phrases[first] = phrases[first] or {}
            table.insert(phrases[first], e)
        end
    end
    for _, list in pairs(phrases) do
        table.sort(list, function(a, b) return #a.words > #b.words end)
    end
    table.sort(stems, function(a, b) return #a.words[1] > #b.words[1] end)
end

local function WithSuffix(value, suffix)
    return (value:gsub("%*", function() return suffix end))
end

--- Whether entry `e` matches the words from `i` on; returns the suffix of a starred last word.
local function Match(e, tokens, i)
    local n = #e.words
    for k = 1, n do
        local t = tokens[i + k - 1]
        if not t then return nil end
        local w = e.words[k]
        if k == n and e.star then
            if t.norm:sub(1, #w) ~= w then return nil end
            return t.word:sub(#w + 1)
        elseif t.norm ~= w then
            return nil
        end
    end
    return ""
end

--- `text` with dictionary entries replaced: phrases first (longest first), then whole words,
--- then stems ("дамагер*" for "дамагера", the ending carried over to the "*" of the value).
function D.Apply(text)
    local tokens, pos = {}, 1
    while true do
        local s, e = text:find(WORD, pos)
        if not s then break end
        local word = text:sub(s, e)
        tokens[#tokens + 1] = { s = s, e = e, word = word, norm = D.Norm(word) }
        pos = e + 1
    end
    local out, last, i = {}, 1, 1
    while i <= #tokens do
        local t = tokens[i]
        local value, span
        for _, e in ipairs(phrases[t.norm] or {}) do
            local suffix = Match(e, tokens, i)
            if suffix then value, span = WithSuffix(e.value, suffix), #e.words break end
        end
        if not value and exact[t.norm] then value, span = exact[t.norm], 1 end
        if not value then
            for _, e in ipairs(stems) do
                local suffix = Match(e, tokens, i)
                if suffix then value, span = WithSuffix(e.value, suffix), 1 break end
            end
        end
        if value then
            out[#out + 1] = text:sub(last, t.s - 1)
            -- marked (\2 ... \3) so the program can decline the replacement after a preposition
            out[#out + 1] = value ~= "" and ("\2" .. value .. "\3") or ""
            last = tokens[i + span - 1].e + 1
            i = i + span
        else
            i = i + 1
        end
    end
    out[#out + 1] = text:sub(last)
    return table.concat(out)
end

--- The replacement for a single word, if the dictionary has one (diagnostics).
function D.Lookup(word)
    return exact[D.Norm(word)]
end

-- Layers. The default (D.DEFAULT) lives in the addon; the player's dictionary is the default with
-- their edits on top, and only the edits are saved - db.dictionaryEdits = {
--     lines = { [key] = "block" },  -- entries changed or added, with the comments above them
--     removed = { [key] = true },   -- default entries deleted
--     header = "...",               -- the comment block at the top, when changed
-- }
-- An entry left as it is is not stored, so a changed default reaches it by itself; an edited one
-- wins over the default; a deleted one stays deleted; a new default entry simply appears. (A
-- default fetched from GitHub can later be a layer between the two.)

--- The identity of a dictionary line: its normalised words ("*" for a stem), or for a regex its
--- pattern - all before the last "=" - so a changed reading is still the same entry. nil for a
--- line that is no entry.
function D.KeyOf(line)
    local trimmed = line:match("^%s*(.-)%s*$")
    if trimmed:sub(1, 1) == "~" then
        return ((trimmed:match("^(.*)=") or trimmed):match("^(.-)%s*$"))
    end
    local key = trimmed:match("^(.-)%s*=")
    if not key or key == "" then return nil end
    local star = key:sub(-1) == "*"
    local words = Words(star and key:sub(1, -2) or key)
    if #words == 0 then return nil end
    return table.concat(words, " ") .. (star and "*" or "")
end

--- `text` cut into its header (the comments at the top) and its entries by key, each with the
--- comments above it: { header = "...", blocks = { [key] = "comments\nline" }, lines = { [key] = "line" } }.
local function Blocks(text)
    local header, blocks, lines, pending, top = {}, {}, {}, {}, true
    for line in ((text or "") .. "\n"):gmatch("(.-)\r?\n") do
        local trimmed = line:match("^%s*(.-)%s*$")
        if trimmed:sub(1, 1) == "#" then
            if top then header[#header + 1] = trimmed else pending[#pending + 1] = trimmed end
        elseif trimmed ~= "" then
            top = false
            local key = D.KeyOf(trimmed) or ("?" .. trimmed)   -- not an entry: kept as it is
            pending[#pending + 1] = trimmed
            local block = table.concat(pending, "\n")
            blocks[key] = blocks[key] and (blocks[key] .. "\n" .. block) or block
            lines[key] = lines[key] and (lines[key] .. "\n" .. trimmed) or trimmed
            pending = {}
        end
    end
    if #pending > 0 then blocks["#"] = table.concat(pending, "\n") end   -- comments after the last entry
    return { header = table.concat(header, "\n"), blocks = blocks, lines = lines }
end

local default, merged
local function Default()
    default = default or Blocks(D.DEFAULT)
    return default
end

--- Forget the cached default and merged text (after D.DEFAULT changes: a new layer, a test).
function D.Invalidate()
    default, merged = nil, nil
end

local function Edits()
    local e = ns.db.dictionaryEdits
    if not e then
        e = { lines = {}, removed = {} }
        ns.db.dictionaryEdits = e
    end
    e.lines, e.removed = e.lines or {}, e.removed or {}
    return e
end

--- The player's dictionary: the default with their edits, sorted as D.Sort sorts (the blocks
--- sorted here, not by D.Sort: it would take the comments of whichever block came first for the
--- header).
function D.Text()
    if merged then return merged end
    local def, e = Default(), Edits()
    local items = {}
    local function Add(block)
        local group, key = SortKey(block:match("([^\n]*)$"))
        items[#items + 1] = { block = block, group = group, key = key }
    end
    for key, block in pairs(def.blocks) do
        if key ~= "#" and not e.removed[key] and not e.lines[key] then Add(block) end
    end
    for key, block in pairs(e.lines) do
        if key ~= "#" then Add(block) end
    end
    table.sort(items, function(x, y)
        if x.group ~= y.group then return x.group < y.group end
        if x.key ~= y.key then return x.key < y.key end
        return x.block < y.block
    end)
    local out = {}
    local header = e.header or def.header
    if header ~= "" then out[#out + 1] = header end
    for _, item in ipairs(items) do out[#out + 1] = item.block end
    local tail = e.lines["#"] or (not e.removed["#"] and def.blocks["#"])
    if tail then out[#out + 1] = tail end
    merged = table.concat(out, "\n") .. "\n"
    return merged
end

--- The edits that make the default into `text`. `same(key, mine, theirs)` says whether an entry
--- is unchanged (by default: its block, comments included, is the default's).
local function Diff(text, same)
    local def, mine = Default(), Blocks(text)
    local e = { lines = {}, removed = {} }
    if mine.header ~= def.header then e.header = mine.header end
    for key, block in pairs(mine.blocks) do
        if not (def.blocks[key] and same(key, mine, def)) then e.lines[key] = block end
    end
    for key in pairs(def.blocks) do
        if not mine.blocks[key] then e.removed[key] = true end
    end
    return e
end

local function SameBlock(key, mine, def) return mine.blocks[key] == def.blocks[key] end

--- The dictionary window's text, saved as edits of the default.
function D.SetText(text)
    ns.db.dictionaryEdits = Diff(text, SameBlock)
    merged = nil
    D.Rebuild()
end

--- Back to the default: no edits.
function D.Reset()
    ns.db.dictionaryEdits = { lines = {}, removed = {} }
    merged = nil
    D.Rebuild()
end

-- Default entries whose key (a regex pattern) changed: old key -> new key. Whoever edited or
-- deleted the old entry keeps their choice: the new default entry does not appear beside it.
D.RENAMED = {}

--- Once per load: the edits' tables in place, and renamed default entries (D.RENAMED) carrying
--- over the player's choice.
function D.Migrate(db)
    db.dictionaryEdits = db.dictionaryEdits or { lines = {}, removed = {} }
    local e = db.dictionaryEdits
    e.lines, e.removed = e.lines or {}, e.removed or {}
    for old, new in pairs(D.RENAMED) do
        if e.removed[old] or e.lines[old] then e.removed[new] = true end
        e.removed[old] = nil
    end
    merged = nil
end

D.DEFAULT = D.Sort(D.DEFAULT)
