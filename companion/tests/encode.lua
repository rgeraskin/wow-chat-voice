-- Test helper (LuaJIT): encode a payload with the addon's Protocol.lua and print the cells as
-- "r g b" lines. Usage: luajit encode.lua <Protocol.lua> <seq> <cells> < payload
local path, seq, cells = arg[1], tonumber(arg[2]), tonumber(arg[3])
local ns = {}
assert(loadfile(path))("WowChatVoice", ns)
local payload = io.read("*a")
local out = ns.Protocol.Encode(seq, payload, cells)
for _, c in ipairs(out) do io.write(c[1], " ", c[2], " ", c[3], "\n") end
