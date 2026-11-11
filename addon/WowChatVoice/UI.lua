-- Small building blocks shared by the addon's windows, so they look alike.
local _, ns = ...

local UI = {}
ns.UI = UI

UI.GOLD = { 1, 0.82, 0 }

function UI.Tooltip(widget, text)
    widget:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(type(text) == "function" and text() or text, 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    widget:SetScript("OnLeave", GameTooltip_Hide)
end

--- A movable window with a title that closes on Escape.
function UI.Window(name, title, width, height, strata)
    local w = CreateFrame("Frame", name, UIParent, "BasicFrameTemplateWithInset")
    w:SetSize(width, height)
    w:SetPoint("CENTER")
    w:SetFrameStrata(strata or "DIALOG")
    w:SetToplevel(true)
    w:SetMovable(true)
    w:EnableMouse(true)
    w:RegisterForDrag("LeftButton")
    w:SetScript("OnDragStart", w.StartMoving)
    w:SetScript("OnDragStop", w.StopMovingOrSizing)
    w:SetClampedToScreen(true)
    w:Hide()
    tinsert(UISpecialFrames, name)
    local t = w:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    t:SetPoint("TOP", 0, -5)
    t:SetText(title)
    w.title = t
    return w
end

--- A section title in gold with a thin rule to the right edge; returns the y below it.
function UI.Header(parent, text, y)
    local label = parent:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    label:SetPoint("TOPLEFT", 18, y)
    label:SetText(text)
    local rule = parent:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(UI.GOLD[1], UI.GOLD[2], UI.GOLD[3], 0.25)
    rule:SetHeight(1)
    rule:SetPoint("LEFT", label, "RIGHT", 8, 0)
    rule:SetPoint("RIGHT", parent, "RIGHT", -18, 0)
    return y - 22
end

--- A check box with a label; `get`/`set` read and write the setting.
function UI.Check(parent, x, y, label, tip, get, set)
    local c = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
    c:SetSize(24, 24)
    c:SetPoint("TOPLEFT", x, y)
    local text = c:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    text:SetPoint("LEFT", c, "RIGHT", 2, 0)
    text:SetText(label)
    c.label = text
    c:SetHitRectInsets(0, -(text:GetStringWidth() + 6), 0, 0)
    c:SetScript("OnClick", function(self) set(self:GetChecked() and true or false) end)
    c.refresh = function() c:SetChecked(get() and true or false) end
    if tip then UI.Tooltip(c, tip) end
    return c
end

function UI.SetCheckEnabled(c, enabled)
    if enabled then c:Enable() else c:Disable() end
    c.label:SetTextColor(enabled and 1 or 0.5, enabled and 1 or 0.5, enabled and 1 or 0.5)
end

function UI.Button(parent, text, width, onClick)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetSize(width, 22)
    b:SetText(text)
    b:SetScript("OnClick", onClick)
    return b
end

--- A dark box with a border, for text fields (falls back to a plain dark panel without
--- BackdropTemplate).
function UI.Box(parent)
    local box
    if BackdropTemplateMixin then
        box = CreateFrame("Frame", nil, parent, "BackdropTemplate")
        box:SetBackdrop({
            bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
            edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
            tile = true, tileSize = 16, edgeSize = 14,
            insets = { left = 4, right = 4, top = 4, bottom = 4 },
        })
        box:SetBackdropColor(0, 0, 0, 0.75)
        box:SetBackdropBorderColor(0.6, 0.6, 0.6, 1)
    else
        box = CreateFrame("Frame", nil, parent)
        local bg = box:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints()
        bg:SetColorTexture(0, 0, 0, 0.75)
    end
    return box
end
