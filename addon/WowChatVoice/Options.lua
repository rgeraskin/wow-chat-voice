-- The settings window (/wcv, the minimap button, Options > AddOns): the main switch on top, then
-- channels, reading and the dictionary (in a window of its own, DictionaryWindow.lua).
local _, ns = ...
local UI = ns.UI

local O = {}
ns.Options = O

local TITLE = "WoW Chat Voice"

-- Channels, in two columns: setting, label, tooltip.
local CHANNELS = {
    { "party", "Группа", "Сообщения группы и её лидера." },
    { "say", "Сказать (/s)", "Что говорят игроки рядом." },
    { "raid", "Рейд", "Сообщения рейда и его лидера." },
    { "yell", "Крик (/y)", "Что кричат игроки рядом." },
    { "warning", "Объявления рейда", "Объявления рейда (/rw)." },
    { "whisper", "Шёпот", "Шёпот вам." },
    { "instance", "Подземелье и БГ", "Чат подземелья (поиск группы) и поля боя." },
    { "guild", "Гильдия", "Чат гильдии." },
    { "officer", "Офицеры", "Офицерский чат гильдии." },
    { "channels", "Общие каналы", "Номерные каналы: Общий, Торговля, Поиск спутников, Оборона." },
    { "emote", "Эмоции (/e)", "Эмоции, написанные игроками." },
    { "self", "Свои сообщения", "Читать и ваши собственные строки." },
}

local window, toggle, verb, lastNames
local checks, radios, sliders = {}, {}, {}

local function Refresh()
    if not window then return end
    toggle:SetText(ns.db.enabled and "|cff40ff40Озвучка чата включена|r" or "|cffff5050Озвучка чата выключена|r")
    for _, c in ipairs(checks) do c.refresh() end
    UI.SetCheckEnabled(verb, ns.db.sayNames)
    UI.SetCheckEnabled(lastNames, ns.db.sayNames)
    for value, r in pairs(radios) do r:SetChecked((ns.db.voices or "f5") == value) end
    for key, sl in pairs(sliders) do
        -- through the minimum: setting the value the slider already has does not move the thumb,
        -- and on the first show it was placed before the slider had its width
        local value = ns.db[key] or sl.default   -- before: SetValue(lo) writes lo into the setting
        sl.slider:SetValue(sl.lo)
        sl.slider:SetValue(value)
        ns.db[key] = value
        sl.show(value)
    end
end

local function Setting(key, after)
    return function() return ns.db[key] end, function(v)
        ns.db[key] = v
        if after then after(v) end
    end
end

local function Build()
    window = UI.Window("WowChatVoiceOptions", TITLE, 420, 584)
    local y = -32

    -- The main switch: a wide button, green or red.
    toggle = UI.Button(window, "", 232, function() ns.SetEnabled(not ns.db.enabled) end)
    toggle:SetHeight(30)
    toggle:SetPoint("TOPLEFT", 18, y)
    local get, set = Setting("minimapIcon", function() ns.Minimap.Update() end)
    checks[#checks + 1] = UI.Check(window, 262, y - 3, "Значок у миникарты",
        "ЛКМ — эти настройки, ПКМ — включить или выключить озвучку.", get, set)
    UI.Tooltip(toggle, "Включить или выключить всю озвучку: полосу у верхнего края экрана и передачу чата "
        .. "программе. То же — ПКМ по значку у миникарты или /wcv on, /wcv off.")
    y = y - 38

    -- Second row, lined up with the first: try it, and hand the race voices out afresh.
    StaticPopupDialogs["WOWCHATVOICE_RESET"] = {
        text = "Раздать голоса рас заново?\n\nПрограмма забудет, у кого какой голос был, и выдаст их снова — "
            .. "так же, без повторов, начиная с тех, кто заговорит первым.",
        button1 = YES, button2 = NO,
        OnAccept = function() ns.ResetVoices() end,
        timeout = 0, whileDead = true, hideOnEscape = true, preferredIndex = 3,
    }
    local test = UI.Button(window, "Проверка", 232, ns.Test)
    test:SetPoint("TOPLEFT", 18, y)
    UI.Tooltip(test, "Четыре тестовые строки разными голосами (/wcv test). Все команды — /wcv help.")
    local reset = UI.Button(window, "Перераздать голоса", 140, function() StaticPopup_Show("WOWCHATVOICE_RESET") end)
    reset:SetPoint("TOPRIGHT", -18, y)
    UI.Tooltip(reset, "Голос расы закрепляется за персонажем навсегда (файл assignments.json программы). "
        .. "Кнопка раздаёт голоса рас заново — например, после смены настроек голосов. То же — /wcv reset.")
    y = y - 40

    y = UI.Header(window, "Каналы", y)
    for i, item in ipairs(CHANNELS) do
        local col, row = (i - 1) % 2, math.floor((i - 1) / 2)
        local get, set = Setting(item[1])
        checks[#checks + 1] = UI.Check(window, 18 + col * 196, y - row * 24, item[2], item[3], get, set)
    end
    y = y - math.ceil(#CHANNELS / 2) * 24
    get, set = Setting("onlyVisible")
    checks[#checks + 1] = UI.Check(window, 18, y, "Только то, что видно в окнах чата", "Читать строку, только если "
        .. "её показывает какое-нибудь из твоих окон (вкладок) чата: его типы сообщений и каналы из настроек чата, "
        .. "и её не скрыл фильтр (антиспам и т. п.). Выключено — всё из отмеченных выше каналов.", get, set)
    y = y - 24 - 10

    y = UI.Header(window, "Чтение", y)
    get, set = Setting("sayNames", function() Refresh() end)
    checks[#checks + 1] = UI.Check(window, 18, y, "Озвучивать имена", "Перед сообщением читать имя написавшего: "
        .. "«Громмаш: всем привет».", get, set)
    get, set = Setting("sayLastNames")
    lastNames = UI.Check(window, 42, y - 24, "и фамилии: «Ивар Седой», а не «Ивар»", "Читать имя целиком. Выключено — "
        .. "только до первого пробела: у персонажа «Ивар Седой» прозвучит «Ивар».", get, set)
    checks[#checks + 1] = lastNames
    get, set = Setting("sayVerb")
    verb = UI.Check(window, 42, y - 48, "с глаголом: «Громмаш говорит: …»", "Вместо двоеточия — что сделал игрок: "
        .. "говорит (/s), кричит (/y), шепчет (шёпот), пишет (остальные каналы).", get, set)
    checks[#checks + 1] = verb
    get, set = Setting("declension")
    checks[#checks + 1] = UI.Check(window, 18, y - 72, "Склонять замены после предлогов", "Программа ставит замены "
        .. "словаря в нужный падеж по предлогу перед ними: «в ОП» — «в Огненную пропасть», «для дд» — «для "
        .. "дамагера» (pymorphy3).", get, set)
    y = y - 102

    local voicesLabel = window:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    voicesLabel:SetPoint("TOPLEFT", 22, y - 4)
    voicesLabel:SetText("Голоса:")
    local function Radio(value, label, tip, x)
        local ok, r = pcall(CreateFrame, "CheckButton", nil, window, "UIRadioButtonTemplate")
        if not ok then r = CreateFrame("CheckButton", nil, window, "UICheckButtonTemplate") end
        r:SetSize(18, 18)
        r:SetPoint("TOPLEFT", x, y - 2)
        local text = r:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        text:SetPoint("LEFT", r, "RIGHT", 4, 0)
        text:SetText(label)
        r:SetHitRectInsets(0, -(text:GetStringWidth() + 6), 0, 0)
        r:SetScript("OnClick", function()
            for v, other in pairs(radios) do other:SetChecked(v == value) end
            if ns.db.voices ~= value then ns.SetVoices(value) end
        end)
        UI.Tooltip(r, tip)
        radios[value] = r
    end
    Radio("f5", "Расы", "Голоса рас из аддона CatQuest через нейросеть F5-TTS: у каждого персонажа свой голос его "
        .. "расы и пола. Нужна видеокарта NVIDIA; без неё программа читает голосами Windows.", 76)
    Radio("sapi", "Windows", "Русские голоса Windows (RHVoice, Silero, Edge): каждому игроку свой голос по имени и "
        .. "полу. Какие раздавать — кнопка справа.", 146)
    local pick = UI.Button(window, "Голоса Windows…", 140, function() ns.VoicesWindow.Toggle() end)
    pick:SetPoint("TOPRIGHT", -18, y)
    y = y - 34


    -- A labelled slider for a percent setting `key`, `lo`..`hi` in steps of `step`.
    local function Slider(key, title, lo, hi, step, tip)
        local label = window:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        label:SetPoint("TOPLEFT", 22, y)
        local slider = CreateFrame("Slider", nil, window)
        slider:SetOrientation("HORIZONTAL")
        slider:SetSize(200, 16)
        slider:SetPoint("TOPRIGHT", -24, y + 2)
        slider:SetMinMaxValues(lo, hi)
        slider:SetValueStep(step)
        slider:SetObeyStepOnDrag(true)
        local track = slider:CreateTexture(nil, "BACKGROUND")
        track:SetColorTexture(1, 1, 1, 0.15)
        track:SetPoint("LEFT")
        track:SetPoint("RIGHT")
        track:SetHeight(4)
        slider:SetThumbTexture("Interface\\Buttons\\UI-SliderBar-Button-Horizontal")
        local function Show(value)
            label:SetText(("%s: |cffffd100%d%%|r"):format(title, value))
        end
        slider:SetScript("OnValueChanged", function(_, value)
            value = math.floor(value / step + 0.5) * step
            ns.db[key] = value
            Show(value)
        end)
        slider:EnableMouseWheel(true)
        slider:SetScript("OnMouseWheel", function(self, delta) self:SetValue(self:GetValue() + delta * step) end)
        UI.Tooltip(slider, tip)
        sliders[key] = { slider = slider, show = Show, default = 100, lo = lo }
        y = y - 34
    end
    Slider("rate", "Скорость чтения", 50, 200, 5,
        "Скорость чтения для всех голосов, от 50 до 200 %. Колесо мыши — шаг 5 %.")
    Slider("volume", "Громкость", 0, 200, 5,
        "Громкость озвучки, от 0 до 200 %: действует со следующей строки. Больше 100 % — усиление (до двух раз, "
        .. "пики сглаживаются, чтобы не хрипело). Колесо мыши — шаг 5 %.")

    y = UI.Header(window, "Словарь", y)
    local note = window:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    note:SetPoint("TOPLEFT", 22, y - 4)
    note:SetWidth(220)
    note:SetJustifyH("LEFT")
    note:SetText("Как читать сленг и сокращения: WTS = продам, дд = дамагер, ОП = Огненная пропасть.")
    local dict = UI.Button(window, "Словарь…", 110, function() ns.DictionaryWindow.Toggle() end)
    dict:SetPoint("TOPRIGHT", -18, y)
    y = y - 44

    window:SetHeight(-y + 10)

    window:SetScript("OnShow", function()
        Refresh()
        if C_Timer then C_Timer.After(0, Refresh) end   -- again once the window is laid out
    end)
end

O.Refresh = function() Refresh() end

function O.Toggle()
    if not window then Build() end
    window:SetShown(not window:IsShown())
end

local function RegisterInGameSettings()
    local panel = CreateFrame("Frame")
    panel.name = TITLE
    local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOPLEFT", 16, -16)
    title:SetText(TITLE)
    local open = UI.Button(panel, "Открыть настройки", 180, function()
        if SettingsPanel and SettingsPanel:IsShown() then pcall(HideUIPanel, SettingsPanel) end
        if not window then Build() end
        window:Show()
    end)
    open:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -12)
    local hint = panel:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    hint:SetPoint("LEFT", open, "RIGHT", 10, 0)
    hint:SetText("или /wcv в чате")
    if Settings and Settings.RegisterCanvasLayoutCategory and Settings.RegisterAddOnCategory then
        Settings.RegisterAddOnCategory(Settings.RegisterCanvasLayoutCategory(panel, panel.name))
    elseif InterfaceOptions_AddCategory then
        InterfaceOptions_AddCategory(panel)
    end
end

function O.Initialize()
    RegisterInGameSettings()
end
