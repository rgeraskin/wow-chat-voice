-- Chat events -> payload for the strip: kind, sender, race, sex, class, channel, options, text,
-- joined by the unit separator (\31); options are "key=value;..." (rate, voice). The companion
-- picks a voice by sender, race and sex.
local ADDON, ns = ...

ns.DEFAULTS = {
    enabled = true,
    party = true,      -- party and party leader
    raid = true,       -- raid and raid leader
    warning = true,    -- raid warnings
    instance = true,   -- instance chat (dungeon finder groups, battlegrounds)
    say = true,
    yell = true,
    whisper = true,    -- whispers to you
    guild = true,
    officer = false,
    channels = false,  -- numbered channels: General, Trade, LookingForGroup, LocalDefense ...
    emote = false,     -- /e emotes
    self = false,      -- your own lines
    onlyVisible = true, -- only lines a chat window of yours shows (its message types and channels, chat filters)
    cell = 2,          -- strip cell size, physical pixels
    rows = 1,          -- strip rows of cells
    -- the strip's cells start at the "left" edge or the "right"; not "right" by default: a minimap at
    -- the top edge draws over the strip there whatever its strata, and long lines get cut
    stripFrom = "left",
    -- dictionaryEdits: the player's changes to the default slang dictionary (Dictionary.lua, layers)
    rate = 100,        -- reading speed, percent of the voice's own pace (50..200)
    volume = 100,      -- loudness, percent (0..200: over 100 the program boosts, easing the peaks), on top of the program's own `volume`
    minimapIcon = true,
    minimapAngle = 160, -- degrees on the minimap ring (CatQuest's sits at 200)
    sayNames = false,  -- "Name: text"
    sayVerb = false,   -- "Name says: text" (says / yells / whispers / writes, by chat kind)
    sayLastNames = false, -- the whole name ("Ивар Седой"); off: up to the first space ("Ивар")
    declension = true, -- the program declines dictionary replacements after prepositions (pymorphy3)
    voices = "f5",     -- "f5": race voices (CatQuest, F5-TTS); "sapi": Windows voices
    -- voiceOff: [Windows voice name] = true for voices switched off; nil until changed here (the
    -- program then uses its own defaults)
}

-- Event -> setting that switches it on.
local EVENTS = {
    CHAT_MSG_PARTY = "party",
    CHAT_MSG_PARTY_LEADER = "party",
    CHAT_MSG_RAID = "raid",
    CHAT_MSG_RAID_LEADER = "raid",
    CHAT_MSG_RAID_WARNING = "warning",
    CHAT_MSG_INSTANCE_CHAT = "instance",
    CHAT_MSG_INSTANCE_CHAT_LEADER = "instance",
    CHAT_MSG_SAY = "say",
    CHAT_MSG_YELL = "yell",
    CHAT_MSG_WHISPER = "whisper",
    CHAT_MSG_GUILD = "guild",
    CHAT_MSG_OFFICER = "officer",
    CHAT_MSG_CHANNEL = "channels",
    CHAT_MSG_EMOTE = "emote",
}

local SEP = "\31"
local VERBS = { say = "говорит", yell = "кричит", whisper = "шепчет", test = "говорит" }
local PREFIX = "|cff66ccffWoW Chat Voice|r: "

--- Chat text without the client's markup: colours, links (their visible text kept), textures,
--- atlases and raid target icons ({rt1}, {череп}).
function ns.Clean(text)
    text = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
    text = text:gsub("|H.-|h(.-)|h", "%1")
    text = text:gsub("|T.-|t", ""):gsub("|A.-|a", "")
    text = text:gsub("{.-}", ""):gsub("||", "|")
    -- A "+" typed in chat is the word; every "+" after this point is a dictionary stress mark.
    text = text:gsub("%+", " плюс ")
    text = text:gsub(SEP, " "):gsub("%s+", " ")
    text = ns.Emoticons(text):gsub("%s+([%?!,%.])", "%1")
    return (text:gsub("^ ", ""):gsub(" $", ""))
end

--- Brackets used for feelings, not as brackets, read as a full stop: ")" "))" "(((" ":)" ":D" ";P".
--- A bracket with its pair in the line stays: "(через 5 мин)".
function ns.Emoticons(text)
    text = text:gsub("[:;=]%-?[%)%(DdPpРр]+", ".")          -- :) :( :D ;) :-P (Р — русская)
    text = text:gsub("[%(%)][%(%)]+", ".")                  -- )) ((( )(
    local opens = select(2, text:gsub("%(", ""))
    local closes = select(2, text:gsub("%)", ""))
    if opens ~= closes then
        text = text:gsub("[%(%)]", ".")                     -- a lone bracket: "привет)"
    end
    text = text:gsub("%s+%.", "."):gsub("%.%.+", "."):gsub("([!?])%.", "%1"):gsub("%.%s*([!?])", "%1")
    return text
end

function ns.Send(kind, sender, race, sex, class, channel, text)
    local raw = (text or ""):gsub(SEP, " ")
    text = ns.Dictionary.Apply(ns.Clean(text or ""))
    text = text:gsub("%s+", " "):gsub("^ ", ""):gsub(" $", "")
    if text == "" then return end
    if ns.db.sayNames and sender and sender ~= "" then
        local name = Ambiguate and Ambiguate(sender, "none") or sender:match("^[^-]+")
        if not ns.db.sayLastNames then name = name:match("^%S+") or name end
        if kind == "emote" then
            text = name .. " " .. text                     -- "Вася смеётся"
        elseif ns.db.sayVerb then
            text = name .. " " .. (VERBS[kind] or "пишет") .. ": " .. text
        else
            text = name .. ": " .. text
        end
    end
    local options = ns.LineOptions() .. (";decl=%d;raw=1"):format(ns.db.declension == false and 0 or 1)
    -- the line as typed goes last, for the program's log: when the strip is short of room, it is
    -- what gets cut, not the text to say
    local payload = table.concat({ kind, sender or "", race or "", tostring(sex or ""), class or "",
        channel or "", options, text, raw }, SEP)
    ns.Strip.Push(payload)
end

--- The options every line carries: speed, loudness and engine ("f5" or "sapi"; `voice` overrides).
function ns.LineOptions(voice)
    return ("rate=%d;vol=%d;voice=%s"):format(ns.db.rate or 100, ns.db.volume or 100, voice or ns.db.voices or "f5")
end

--- A line the companion does not speak: the current settings (which voices to keep loaded, which
--- Windows voices are off).
function ns.SendControl()
    local options = ns.LineOptions()
    if ns.db.voiceOff then
        local off = {}
        for name in pairs(ns.db.voiceOff) do off[#off + 1] = name end
        table.sort(off)
        options = options .. ";off=" .. table.concat(off, "|")
    end
    ns.Strip.Push(table.concat({ "control", "", "", "", "", "", options, "-" }, SEP))
end

-- The dictionary's regular expressions go to the program over the strip, in parts of at most
-- REGEX_PART bytes (cut at line ends), tagged with a checksum of the whole set: "id=..;part=i;of=n".
-- Sent when they change (2 s after the last edit), at login, and every 2 minutes for a program
-- started after the game. Before this the program read them from the saved variables, which the
-- game writes only on /reload and logout.
local REGEX_PART = 480
local lastRegexes

--- The regex set as sent (one per line, "-" for none) and its id (CRC-16, hex).
local function RegexSet()
    local text = table.concat(ns.Dictionary.Regexes(), "\n")
    if text == "" then text = "-" end
    local bytes = {}
    for i = 1, #text do bytes[i] = text:byte(i) end
    return text, ("%04x"):format(ns.Protocol.CRC16(bytes))
end

function ns.SendRegexes(force)
    local text, id = RegexSet()
    if not force and id == lastRegexes then return end
    lastRegexes = id
    local parts, current = {}, ""
    for line in (text .. "\n"):gmatch("(.-)\n") do
        line = ns.Protocol.TrimUTF8(line, REGEX_PART)
        if current ~= "" and #current + 1 + #line > REGEX_PART then
            parts[#parts + 1] = current
            current = line
        else
            current = current == "" and line or (current .. "\n" .. line)
        end
    end
    parts[#parts + 1] = current
    for i, part in ipairs(parts) do
        local options = ("id=%s;part=%d;of=%d"):format(id, i, #parts)
        ns.Strip.Push(table.concat({ "regex", "", "", "", "", "", options, part }, SEP))
    end
end

local regexTimer
function ns.RegexesChanged()
    if not (C_Timer and ns.Strip and ns.db) then return end
    if regexTimer then regexTimer:Cancel() end
    regexTimer = C_Timer.NewTimer(2, function() regexTimer = nil; ns.SendRegexes(false) end)
end

--- Ask the program to forget which race voice each character had and hand them out afresh.
function ns.ResetVoices()
    local options = ns.LineOptions()
    ns.Strip.Push(table.concat({ "reset", "", "", "", "", "", options, "-" }, SEP))
    print(PREFIX .. "голоса рас будут розданы заново: каждый персонаж получит голос, когда заговорит.")
end

--- A test line in one Windows voice (the voices window's play buttons).
function ns.TestVoice(name)
    local options = ns.LineOptions("sapi") .. ";sapi=" .. name
    ns.Strip.Push(table.concat({ "test", "Проверка", "", "", "", "", options,
        "Привет! Нужен дам+агер в Мёртвые копи, продам сумки за пять тысяч." }, SEP))
end


function ns.SetVoices(value)
    ns.db.voices = value
    ns.SendControl()
    if value == "f5" then
        print(PREFIX .. "голоса рас (CatQuest). Программа загружает модель — около 15 секунд, пока читают голоса Windows.")
    else
        print(PREFIX .. "голоса Windows. Программа выгружает модель голосов рас.")
    end
end

-- The last chat lines read, as they came (before the dictionary), for /wcv last N.
local HISTORY = 50
ns.history = {}

local function Remember(...)
    table.insert(ns.history, { ... })
    if #ns.history > HISTORY then table.remove(ns.history, 1) end
end

--- Read the last `n` chat lines again, through the current dictionary and settings.
function ns.Replay(n)
    n = math.max(1, math.min(n or 5, #ns.history))
    if #ns.history == 0 then
        print(PREFIX .. "пока нечего повторять: ни одной прочитанной строки чата.")
        return
    end
    for i = #ns.history - n + 1, #ns.history do ns.Send(unpack(ns.history[i])) end
    print(PREFIX .. ("повторяю последние строки: %d."):format(n))
end

--- Whether chat window `frame` takes this kind of line: its message types (Chat settings), or for
--- a channel line its channels - matched the way the game's chat frame matches them (zone channel
--- id, else the channel's base name).
local function Takes(frame, event, zoneChannel, baseName)
    if event == "CHAT_MSG_CHANNEL" then
        for index, name in pairs(frame.channelList or {}) do
            if (zoneChannel and zoneChannel > 0 and frame.zoneChannelList
                    and frame.zoneChannelList[index] == zoneChannel)
                or (baseName and name and name:upper() == baseName:upper()) then
                return true
            end
        end
        return false
    end
    local group = (ChatTypeGroupInverted and ChatTypeGroupInverted[event]) or event:sub(10)
    for _, g in pairs(frame.messageTypeList or {}) do
        if g == group then return true end
    end
    return false
end

--- Whether the player sees this line: some chat window that is open (shown or docked as a tab)
--- takes it, and no chat filter - spam blockers and the like - hides it there.
local function Visible(event, ...)
    if not ns.db.onlyVisible or not GetChatWindowInfo then return true end
    local zoneChannel, baseName = select(7, ...), select(9, ...)
    local seen
    for i = 1, NUM_CHAT_WINDOWS or 10 do
        local frame = _G["ChatFrame" .. i]
        local shown, _, docked = select(7, GetChatWindowInfo(i))
        if frame and (shown or docked) and Takes(frame, event, zoneChannel, baseName) then
            seen = frame
            break
        end
    end
    if not seen then return false end
    local filters = ChatFrame_GetMessageEventFilters and ChatFrame_GetMessageEventFilters(event)
    for _, filter in ipairs(filters or {}) do
        local ok, hide = pcall(filter, seen, event, ...)
        if ok and hide then return false end
    end
    return true
end

local function OnChat(event, text, sender, _, channelString, _, _, _, _, _, _, _, guid)
    local db = ns.db
    local key = EVENTS[event]
    if not (db.enabled and key and db[key]) then return end
    if guid and guid ~= "" and guid == UnitGUID("player") and not db.self then return end
    local race, sex, class
    if guid and guid ~= "" then
        local ok, _, englishClass, _, englishRace, gender = pcall(GetPlayerInfoByGUID, guid)
        if ok then race, sex, class = englishRace, gender, englishClass end
    end
    local channel = event == "CHAT_MSG_CHANNEL" and channelString or ""
    Remember(key, sender, race, sex, class, channel, text)
    ns.Send(key, sender, race, sex, class, channel, text)
end

local TESTS = {
    { "Громмаш", "Orc", 2, "WARRIOR", "Всем привет! Кто идёт в Мёртвые копи?" },
    { "Джайна", "Human", 3, "MAGE", "Нужен хил в пещеры, пишите в личку." },
    { "Брэнн", "Dwarf", 2, "HUNTER", "Куплю землекорень, пять штук." },
    { "Тиранда", "NightElf", 3, "PRIEST", "Готовы? Пулю через три секунды." },
}

function ns.Test()
    for _, t in ipairs(TESTS) do ns.Send("test", t[1], t[2], t[3], t[4], "", t[5]) end
    print("|cff66ccffWoW Chat Voice|r: отправлено " .. #TESTS .. " тестовых строки.")
end

--- Silence now: the program cuts the line being said and drops what is waiting (/wcv stop).
function ns.Stop()
    local options = ns.LineOptions()
    ns.Strip.PushNow(table.concat({ "stop", "", "", "", "", "", options, "-" }, SEP))
end

function ns.SetEnabled(enabled)
    ns.db.enabled = enabled and true or false
    if ns.db.enabled then
        ns.Strip.SetShown(true)
    else
        -- the stop has to be on the strip long enough to be read before the strip goes
        ns.Stop()
        if C_Timer then
            C_Timer.After(0.5, function() if not ns.db.enabled then ns.Strip.SetShown(false) end end)
        else
            ns.Strip.SetShown(false)
        end
    end
    if ns.Minimap then ns.Minimap.Refresh() end
    if ns.Options.Refresh then ns.Options.Refresh() end
    print(PREFIX .. "озвучка чата " .. (ns.db.enabled and "включена" or "выключена"))
end

local function Merge(into, defaults)
    for k, v in pairs(defaults) do
        if into[k] == nil then into[k] = v end
    end
    return into
end

local loader = CreateFrame("Frame")
loader:RegisterEvent("ADDON_LOADED")
loader:SetScript("OnEvent", function(self, event, name, ...)
    if event == "ADDON_LOADED" then
        if name ~= ADDON then return end
        WowChatVoiceDB = Merge(WowChatVoiceDB or {}, ns.DEFAULTS)
        ns.db = WowChatVoiceDB
        ns.Dictionary.Migrate(ns.db)
        ns.Dictionary.Rebuild()
        ns.Strip.Initialize()
        ns.Options.Initialize()
        ns.Minimap.Update()
        self:UnregisterEvent("ADDON_LOADED")
        for e in pairs(EVENTS) do self:RegisterEvent(e) end
        self:RegisterEvent("PLAYER_LOGIN")
        return
    end
    if event == "PLAYER_LOGIN" then
        ns.SendControl()   -- the companion loads the voices chosen here
        ns.SendRegexes(true)
        -- the set the saved variables hold now (they are written at login and /reload)
        local _, saved = RegexSet()
        if C_Timer and C_Timer.NewTicker then
            -- For a program started after the game: the settings (a short frame) every 2 minutes.
            -- The regexes - several frames half a screen long - only when they changed in this
            -- session: otherwise the program reads the very same set from the saved variables.
            C_Timer.NewTicker(120, function()
                ns.SendControl()
                local _, now = RegexSet()
                if now ~= saved then ns.SendRegexes(true) end
            end)
        end
        return
    end
    if EVENTS[event] and ns.db.enabled and not Visible(event, name, ...) then return end
    OnChat(event, name, ...)
end)

SLASH_WOWCHATVOICE1 = "/wcv"
SlashCmdList.WOWCHATVOICE = function(msg)
    msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
    if msg == "help" or msg == "?" then
        local G = "|cffffd100"
        print(PREFIX .. "команды:")
        print("  " .. G .. "/wcv|r — окно настроек (то же: значок у миникарты)")
        print("  " .. G .. "/wcv on|r, " .. G .. "/wcv off|r — включить или выключить озвучку (выключение сразу обрывает фразу)")
        print("  " .. G .. "/wcv stop|r — замолчать сейчас и очистить очередь, не выключая")
        print("  " .. G .. "/wcv test|r — четыре тестовые строки разными голосами")
        print("  " .. G .. "/wcv last 5|r — ещё раз прочитать последние 5 строк чата (через текущий словарь)")
        print("  " .. G .. "/wcv reset|r — раздать голоса рас заново")
        print("  " .. G .. "/wcv help|r — этот список")
    elseif msg == "test" then
        ns.Test()
    elseif msg == "stop" then
        ns.Stop()
        print(PREFIX .. "замолкаю (очередь очищена).")
    elseif msg == "reset" then
        ns.ResetVoices()
    elseif msg:match("^last") then
        ns.Replay(tonumber(msg:match("%d+")) or 5)
    elseif msg == "on" or msg == "off" then
        ns.SetEnabled(msg == "on")
    else
        ns.Options.Toggle()
    end
end
