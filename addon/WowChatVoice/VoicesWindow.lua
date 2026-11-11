-- "Голоса Windows": which of the program's Windows voices characters get, each with a play button,
-- a filter (name, engine or sex: "silero", "edge", "жен") and on/off for all the voices shown.
-- The list comes from VoiceList.lua, which the program writes (WoW reads it at start and /reload).
local _, ns = ...
local UI = ns.UI

local V = {}
ns.VoicesWindow = V

local ROW = 24
local window, content, filter, count, empty
local rows = {}

local function List()
    return WowChatVoiceVoiceList or {}
end

local function IsOn(entry)
    if ns.db.voiceOff then return not ns.db.voiceOff[entry.name] end
    return entry.on ~= false
end

--- The first change here makes the program's defaults the addon's own list.
local function SetOn(entry, on)
    if not ns.db.voiceOff then
        ns.db.voiceOff = {}
        for _, e in ipairs(List()) do
            if e.on == false then ns.db.voiceOff[e.name] = true end
        end
    end
    ns.db.voiceOff[entry.name] = (not on) and true or nil
end

local function GenderText(entry)
    return entry.gender == "Male" and "муж." or entry.gender == "Female" and "жен." or ""
end

local function Matches(entry, text)
    if text == "" then return true end
    local haystack = ns.Dictionary.Norm((entry.label or entry.name) .. " " .. GenderText(entry))
    return haystack:find(ns.Dictionary.Norm(text), 1, true) ~= nil
end

local function Shown()
    local text = filter and filter:GetText() or ""
    local out = {}
    for _, entry in ipairs(List()) do
        if Matches(entry, text) then out[#out + 1] = entry end
    end
    return out
end

local function Refresh()
    local list, shown = List(), Shown()
    empty:SetShown(#list == 0)
    local on = 0
    for _, e in ipairs(list) do if IsOn(e) then on = on + 1 end end
    count:SetText(#list > 0 and ("включено %d из %d"):format(on, #list) or "")
    for i, entry in ipairs(shown) do
        local row = rows[i]
        row.entry = entry
        row.check:SetChecked(IsOn(entry))
        row.text:SetText(entry.label or entry.name)
        row.gender:SetText(GenderText(entry))
        row:Show()
    end
    for i = #shown + 1, #rows do rows[i]:Hide() end
    content:SetHeight(math.max(10, #shown * ROW))
end

local function SetAllShown(on)
    for _, entry in ipairs(Shown()) do SetOn(entry, on) end
    ns.SendControl()
    Refresh()
end

local function Build()
    window = UI.Window("WowChatVoiceVoices", "Голоса Windows", 400, 500, "FULLSCREEN_DIALOG")
    window:SetPoint("CENTER", 340, 0)

    local note = window:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    note:SetPoint("TOPLEFT", 18, -32)
    note:SetPoint("RIGHT", -18, 0)
    note:SetJustifyH("LEFT")
    note:SetText("Отмеченные голоса раздаются игрокам (по имени и полу), когда выбраны голоса Windows. "
        .. "«>» — послушать.")

    filter = CreateFrame("EditBox", nil, window, "InputBoxTemplate")
    filter:SetHeight(20)
    filter:SetPoint("TOPLEFT", 24, -64)
    filter:SetWidth(170)
    filter:SetAutoFocus(false)
    local placeholder = filter:CreateFontString(nil, "OVERLAY", "GameFontDisable")
    placeholder:SetPoint("LEFT", 2, 0)
    placeholder:SetText("фильтр: silero, edge, жен…")
    filter:SetScript("OnTextChanged", function(self)
        placeholder:SetShown(self:GetText() == "")
        Refresh()
    end)
    filter:SetScript("OnEscapePressed", function(self)
        self:SetText("")
        self:ClearFocus()
    end)
    UI.Tooltip(filter, "Показать голоса, в названии которых есть этот текст: имя, движок (RHVoice, Silero, Edge) "
        .. "или пол (муж., жен.). «Вкл. все» и «Выкл. все» действуют на показанные.")
    local allOn = UI.Button(window, "Вкл. все", 82, function() SetAllShown(true) end)
    allOn:SetPoint("LEFT", filter, "RIGHT", 10, 0)
    local allOff = UI.Button(window, "Выкл. все", 82, function() SetAllShown(false) end)
    allOff:SetPoint("LEFT", allOn, "RIGHT", 4, 0)

    local box = UI.Box(window)
    box:SetPoint("TOPLEFT", 14, -92)
    box:SetPoint("BOTTOMRIGHT", -14, 36)
    local scroll = CreateFrame("ScrollFrame", nil, box, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 8, -8)
    scroll:SetPoint("BOTTOMRIGHT", -28, 8)
    content = CreateFrame("Frame", nil, scroll)
    content:SetSize(320, 10)
    scroll:SetScrollChild(content)

    for i = 1, #List() do
        local row = CreateFrame("Frame", nil, content)
        row:SetSize(330, ROW)
        row:SetPoint("TOPLEFT", 0, -(i - 1) * ROW)
        row.check = CreateFrame("CheckButton", nil, row, "UICheckButtonTemplate")
        row.check:SetSize(22, 22)
        row.check:SetPoint("LEFT", 0, 0)
        row.check:SetScript("OnClick", function(self)
            SetOn(row.entry, self:GetChecked())
            ns.SendControl()
            Refresh()
        end)
        row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        row.text:SetPoint("LEFT", row.check, "RIGHT", 4, 0)
        row.gender = row:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
        row.gender:SetPoint("RIGHT", -34, 0)
        row.play = UI.Button(row, ">", 26, function() ns.TestVoice(row.entry.name) end)
        row.play:SetHeight(20)
        row.play:SetPoint("RIGHT", 0, 0)
        rows[i] = row
    end

    count = window:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    count:SetPoint("BOTTOMLEFT", 20, 14)

    empty = window:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    empty:SetPoint("CENTER")
    empty:SetWidth(320)
    empty:SetText("Список пуст: запустите программу озвучки (она запишет голоса в аддон) и сделайте /reload.")

    window:SetScript("OnShow", Refresh)
end

function V.Toggle()
    if not window then Build() end
    window:SetShown(not window:IsShown())
    if window:IsShown() then window:Raise() end
end
