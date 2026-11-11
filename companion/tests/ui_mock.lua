-- Minimal WoW API stubs: run the addon's files and open every window, to catch nil calls and typos.
local function widget()
    local w = { _text = "", _shown = false, _checked = false, _scripts = {} }
    return setmetatable(w, { __index = function(t, k)
        if k == "GetText" then return function(self) return self._text end end
        if k == "SetText" then return function(self, v) self._text = v or "" end end
        if k == "GetHeight" or k == "GetWidth" or k == "GetStringWidth" then return function() return 100 end end
        if k == "GetChecked" then return function(self) return self._checked end end
        if k == "SetChecked" then return function(self, v) self._checked = v end end
        if k == "IsShown" then return function(self) return self._shown end end
        if k == "SetShown" then return function(self, v) self._shown = v; if v and self._scripts.OnShow then self._scripts.OnShow(self) end end end
        if k == "Show" then return function(self) self:SetShown(true) end end
        if k == "SetScript" then return function(self, n, f) self._scripts[n] = f end end
        if k == "GetScript" then return function(self, n) return self._scripts[n] end end
        if k == "GetValue" then return function(self) return self._value or 100 end end
        if k == "SetValue" then return function(self, v)
            self._value = v
            if self._scripts.OnValueChanged then self._scripts.OnValueChanged(self, v) end
        end end
        if k:match("^Create") then return function() return widget() end end
        return function() end
    end })
end
local frames = {}
CreateFrame = function() local f = widget(); frames[#frames + 1] = f; return f end
UIParent, WorldFrame, Minimap, GameTooltip = widget(), widget(), widget(), widget()
UISpecialFrames, SlashCmdList, StaticPopupDialogs = {}, {}, {}
StaticPopup_Show = function() end
YES, NO = "Да", "Нет"
tinsert = table.insert
GameTooltip_Hide = function() end
GetPhysicalScreenSize = function() return 2360, 1640 end
GetTime = function() return 0 end
UnitGUID = function() return "me" end
BackdropTemplateMixin = {}
C_Timer = { NewTimer = function(_, f) return { Cancel = function() end } end, NewTicker = function() end,
            After = function(_, f) f() end }
Settings = { RegisterCanvasLayoutCategory = function() return {} end, RegisterAddOnCategory = function() end }
local ns = {}
for _, f in ipairs({ "Protocol.lua", "Strip.lua", "Dictionary.lua", "VoiceList.lua", "Core.lua", "UI.lua",
                     "DictionaryWindow.lua", "Options.lua", "VoicesWindow.lua", "Minimap.lua" }) do
    assert(loadfile(f))("WowChatVoice", ns)
end
WowChatVoiceVoiceList = { { name = "Anna", label = "Anna (RHVoice)", gender = "Female", on = true },
                          { name = "Aidar (Russian)", label = "Aidar (Silero)", gender = "Male", on = true } }
ns.db = setmetatable({ rate = 100, voices = "f5", enabled = true,
                       sayNames = true, sayVerb = true, minimapIcon = true }, {})
ns.Dictionary.Migrate(ns.db)
ns.Dictionary.Rebuild()
local sent = {}
ns.Strip.Push = function(p) sent[#sent + 1] = p end
ns.Options.Initialize()
ns.db.volume = 150
ns.Options.Toggle(); assert(ns.db.volume == 150 and ns.db.rate == 100, "Refresh must keep the settings")
print("options ok")
ns.DictionaryWindow.Toggle(); print("dictionary ok")
ns.VoicesWindow.Toggle(); print("voices ok")
ns.Minimap.Update(); print("minimap ok")
ns.Send("say", "Ивар Седой-Степи", "Orc", 3, "WARRIOR", "", "всем привет")
ns.db.sayLastNames = true
ns.Send("say", "Ивар Седой-Степи", "Orc", 3, "WARRIOR", "", "и фамилия")
ns.db.sayLastNames = false
ns.Send("yell", "Вася-Степи", "Orc", 2, "WARRIOR", "", "АААА")
ns.Send("emote", "Вася-Степи", "Orc", 2, "WARRIOR", "", "смеётся")
ns.db.sayVerb = false
ns.Send("party", "Вася-Степи", "Orc", 2, "WARRIOR", "", "го")
for _, p in ipairs(sent) do print((p:gsub("\31", " | "):gsub("[\2\3]", ""))) end

-- Only what the chat windows show: window 1 is open (say, party, the zone channel "Общий"),
-- window 2 (guild) is closed, and a chat filter hides lines with "спам".
NUM_CHAT_WINDOWS = 2
ChatFrame1 = { messageTypeList = { "SAY", "PARTY" }, channelList = { "Общий" }, zoneChannelList = { 1 } }
ChatFrame2 = { messageTypeList = { "GUILD" }, channelList = {}, zoneChannelList = {} }
GetChatWindowInfo = function(i)
    if i == 1 then return "Общий", 14, 1, 1, 1, 1, true, false, 1 end
    return "Гильдия", 14, 1, 1, 1, 1, false, false, nil
end
ChatFrame_GetMessageEventFilters = function() return { function(_, _, msg) return msg:find("спам") ~= nil end } end
for k, v in pairs({ say = true, yell = true, guild = true, channels = true, onlyVisible = true, sayNames = false }) do
    ns.db[k] = v
end
local loader
for _, f in ipairs(frames) do
    if f._scripts.OnEvent and not loader then loader = f end
end
local function fire(event, msg, zoneId, base)
    sent = {}
    ns.Strip.Push = function(p) sent[#sent + 1] = p end
    loader._scripts.OnEvent(loader, event, msg, "Вася-Степи", "", base and ("1. " .. base) or "", "", "", zoneId or 0,
        0, base or "", nil, 1, "")
    return #sent == 1
end
local cases = {
    { "CHAT_MSG_SAY", "привет", nil, nil, true },
    { "CHAT_MSG_YELL", "кричу", nil, nil, false },             -- no window takes yells
    { "CHAT_MSG_GUILD", "гильдия", nil, nil, false },          -- its window is closed
    { "CHAT_MSG_CHANNEL", "в общем", 1, "Общий", true },
    { "CHAT_MSG_CHANNEL", "в торговле", 0, "Торговля", false }, -- not in any window
    { "CHAT_MSG_SAY", "это спам", nil, nil, false },           -- hidden by a chat filter
}
for _, c in ipairs(cases) do
    assert(fire(c[1], c[2], c[3], c[4]) == c[5], c[1] .. " " .. c[2])
end
ns.db.onlyVisible = false
assert(fire("CHAT_MSG_YELL", "кричу"), "everything when the option is off")
print("visible ok")
