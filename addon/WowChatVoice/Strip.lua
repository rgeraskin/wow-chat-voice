-- The strip: a black bar along the top edge of the screen, `cell` physical pixels high per row,
-- with near-black coloured cells on it that carry the latest chat line (Protocol.lua): the whole
-- bar reads as one dark line. A line's cells are held at least HOLD seconds so the reader catches
-- each one, then IDLE_AFTER the strip goes back to an empty frame (14 cells), which tells the
-- program the addon is there.
local _, ns = ...
local P = ns.Protocol

local S = {}
ns.Strip = S

local HOLD = 0.25      -- seconds each line stays up before the next queued one
local IDLE_AFTER = 0.5 -- then, with nothing queued, the strip goes back to an empty frame (the
                       -- program grabs the window 20 times a second: 0.25 s is enough for it)
local MAX_QUEUE = 20   -- lines waiting beyond this are dropped, oldest first

local frame, background
local textures = {}
local painted = 0      -- cells coloured by the last paint
local perRow, total, unit, cellPx = 0, 0, 1, 2
local queue = {}
local lastShown = 0
local seq = math.random(0, 65535)

--- Cells run from the left edge rightwards by default, or from the right edge leftwards; the
--- program reads either. (On the right a minimap at the top edge covers them: it draws over every
--- frame there, so a long line is cut.)
local function Place(i)
    local t = textures[i]
    local col = (i - 1) % perRow
    local row = math.floor((i - 1) / perRow)
    t:ClearAllPoints()
    t:SetSize(cellPx * unit, cellPx * unit)
    if ns.db.stripFrom == "right" then
        t:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -col * cellPx * unit, -row * cellPx * unit)
    else
        t:SetPoint("TOPLEFT", frame, "TOPLEFT", col * cellPx * unit, -row * cellPx * unit)
    end
end

--- Size the strip to the screen in physical pixels: at scale 1 the screen is 768 units high.
function S.Layout()
    if not frame then return end
    local physW, physH = GetPhysicalScreenSize()
    unit = 768 / physH
    cellPx = ns.db.cell
    perRow = math.floor(physW / cellPx)
    total = perRow * ns.db.rows
    frame:ClearAllPoints()
    frame:SetPoint("TOPLEFT", WorldFrame, "TOPLEFT", 0, 0)
    frame:SetSize(physW * unit, cellPx * ns.db.rows * unit)
    for i = 1, #textures do Place(i) end
end

local function Paint(cells)
    for i = 1, #cells do
        local t = textures[i]
        if not t then
            t = frame:CreateTexture(nil, "OVERLAY")
            textures[i] = t
            Place(i)
        end
        local c = cells[i]
        t:SetColorTexture(P.LEVELS[c[1] + 1] / 255, P.LEVELS[c[2] + 1] / 255, P.LEVELS[c[3] + 1] / 255, 1)
        t:Show()
    end
    for i = #cells + 1, painted do textures[i]:Hide() end
    painted = #cells
end

local idle = true

local function OnUpdate()
    local now = GetTime()
    if #queue == 0 then
        -- the coloured cells are only up while the program needs to read them
        if not idle and now - lastShown >= IDLE_AFTER then
            seq = (seq + 1) % 65536
            Paint((P.Encode(seq, "", total)))
            idle = true
        end
        return
    end
    if now - lastShown < HOLD then return end
    Paint(table.remove(queue, 1))
    lastShown = now
    idle = false
end

--- Queue a payload (UTF-8 text) for the strip. Returns the payload as it will be sent (trimmed).
function S.Push(payload)
    seq = (seq + 1) % 65536
    local cells, sent = P.Encode(seq, payload, total)
    queue[#queue + 1] = cells
    while #queue > MAX_QUEUE do table.remove(queue, 1) end
    return sent
end

--- Put a payload ahead of everything queued and show it now (a stop must not wait its turn).
function S.PushNow(payload)
    seq = (seq + 1) % 65536
    local cells = P.Encode(seq, payload, total)
    queue = { cells }
    lastShown = 0
end

function S.SetShown(shown)
    if frame then frame:SetShown(shown) end
end

function S.Initialize()
    frame = CreateFrame("Frame", "WowChatVoiceStrip", WorldFrame)
    frame:SetIgnoreParentScale(true)
    frame:SetScale(1)
    frame:SetFrameStrata("TOOLTIP")
    frame:SetFrameLevel(9000)
    frame:EnableMouse(false)
    background = frame:CreateTexture(nil, "BACKGROUND")
    background:SetAllPoints()
    background:SetColorTexture(0, 0, 0, 1)
    S.Layout()
    -- Something on the strip from the start: an empty line under a fresh sequence number, so the
    -- reader sees the addon is there without saying anything.
    Paint((P.Encode(seq, "", total)))
    frame:SetScript("OnUpdate", OnUpdate)
    frame:RegisterEvent("DISPLAY_SIZE_CHANGED")
    frame:RegisterEvent("UI_SCALE_CHANGED")
    frame:SetScript("OnEvent", function() S.Layout() end)
    S.SetShown(ns.db.enabled)
end
