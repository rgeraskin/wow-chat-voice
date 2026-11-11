-- Wire format of the pixel strip (see README.md, "Protocol"). Pure functions only: this file is
-- also loaded by the round-trip test outside the game (LuaJIT, which has the same `bit` library).
local _, ns = ...
ns = ns or {}

local band, bxor, lshift, rshift = bit.band, bit.bxor, bit.lshift, bit.rshift

local P = {}
ns.Protocol = P

P.VERSION = 1
-- Channel brightness of the four levels (0..255): very dark, so the cells melt into the black bar
-- (at 0..72 a green or purple cell stood out in the game). The program takes its thresholds from
-- the calibration cells, so these can change; steps of 12 stay apart up to a game gamma of ~1.2.
P.LEVELS = { 0, 12, 24, 36 }
-- Two sync cells, then four calibration cells (every channel at level 0, 1, 2, 3).
P.HEADER_CELLS = 6
-- version (4 bits), sequence (16), payload length in bytes (12), CRC-16 (16).
P.HEADER_BITS = 48
P.BITS_PER_CELL = 6

--- CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over a list of bytes.
function P.CRC16(bytes)
    local crc = 0xFFFF
    for i = 1, #bytes do
        crc = bxor(crc, lshift(bytes[i], 8))
        for _ = 1, 8 do
            if band(crc, 0x8000) ~= 0 then
                crc = band(bxor(lshift(crc, 1), 0x1021), 0xFFFF)
            else
                crc = band(lshift(crc, 1), 0xFFFF)
            end
        end
    end
    return crc
end

--- How many payload bytes fit in `cells` cells.
function P.MaxBytes(cells)
    local bytes = math.floor(((cells - P.HEADER_CELLS) * P.BITS_PER_CELL - P.HEADER_BITS) / 8)
    return math.max(0, math.min(bytes, 4095))
end

--- `s` cut to at most `n` bytes without splitting a UTF-8 character.
function P.TrimUTF8(s, n)
    if #s <= n then return s end
    local cut = n
    while cut > 0 do
        local b = s:byte(cut + 1)
        if not b or b < 0x80 or b >= 0xC0 then break end
        cut = cut - 1
    end
    return s:sub(1, cut)
end

--- The cells (each { r, g, b } as level indices 0..3) that carry `payload` under sequence number
--- `seq` (0..65535), for a strip of `cells` cells. Returns the cells and the payload as sent
--- (trimmed to fit).
function P.Encode(seq, payload, cells)
    payload = P.TrimUTF8(payload, P.MaxBytes(cells))
    local bytes = { math.floor(seq / 256), seq % 256 }
    for i = 1, #payload do bytes[#bytes + 1] = payload:byte(i) end
    local crc = P.CRC16(bytes)

    local bits = {}
    local function put(value, count)
        for i = count - 1, 0, -1 do bits[#bits + 1] = band(rshift(value, i), 1) end
    end
    put(P.VERSION, 4)
    put(seq, 16)
    put(#payload, 12)
    put(crc, 16)
    for i = 1, #payload do put(payload:byte(i), 8) end
    while #bits % P.BITS_PER_CELL ~= 0 do bits[#bits + 1] = 0 end

    local out = { { 3, 0, 3 }, { 0, 3, 0 }, { 0, 0, 0 }, { 1, 1, 1 }, { 2, 2, 2 }, { 3, 3, 3 } }
    for i = 1, #bits, 6 do
        out[#out + 1] = {
            bits[i] * 2 + bits[i + 1],
            bits[i + 2] * 2 + bits[i + 3],
            bits[i + 4] * 2 + bits[i + 5],
        }
    end
    return out, payload
end

return P
