-- Chapter 14 probe.
-- Phase 1: pack_color and pack_vertex are called DIRECTLY (tools/verify-lib/directcall.lua) with random arguments
--   (negative coordinates, garbage in the top byte of the colour); the record's v0 is the result.
-- Phase 2: the real program runs to `done`. Every word written to GP0 (0x1F801810) and GP1 (0x1F801814) is logged
--   with the number of GPUSTAT reads (lw from 0x1F801814) so far. The value of a write is the source register of the
--   `sw` at the faulting pc (decoded here), because the breakpoint callback does not get it.
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd, rnd32 = DC.rnd, DC.rnd32
local GP0, GP1 = 0x1F801810, 0x1F801814

local log, reads = {}, 0
local function reg_value(pc)
  local w = verify.u32(pc % 0x200000 + 0x80000000)
  local op, rt = bit.rshift(w, 26), bit.band(bit.rshift(w, 16), 31)
  return DC.regget(rt), op
end
local function on_write(port)
  return function(addr, width)
    local pc = tonumber(PCSX.getRegisters().pc) % 4294967296
    local ok, v, op = pcall(reg_value, pc)
    if #log < 3000 then log[#log + 1] = { port, ok and v or -1, ok and op or -1, reads } end
  end
end
local keep = {
  PCSX.addBreakpoint(GP0, 'Write', 4, 'ch14 gp0', on_write(0)),
  PCSX.addBreakpoint(GP1, 'Write', 4, 'ch14 gp1', on_write(1)),
  PCSX.addBreakpoint(GP1, 'Read', 4, 'ch14 stat', function() reads = reads + 1 end),
}

local calls = {}
local function s11() return rnd(2048) - 1024 end          -- signed 11-bit range
for i = 1, 8 do
  calls[#calls + 1] = { fn = 'pack_color', a0 = rnd32(), a1 = rnd(256) }
end
calls[#calls + 1] = { fn = 'pack_color', a0 = 0x00FF8001, a1 = 0x30 }
for i = 1, 8 do
  calls[#calls + 1] = { fn = 'pack_vertex', a0 = s11(), a1 = s11() }
end
calls[#calls + 1] = { fn = 'pack_vertex', a0 = -1, a1 = -1 }
calls[#calls + 1] = { fn = 'pack_vertex', a0 = -90, a1 = 100 }
calls[#calls + 1] = { fn = 'pack_vertex', a0 = 319, a1 = 239 }
for _, c in ipairs(calls) do c.limit = 200 end

local d
d = DC.new{ calls = calls, routines = { 'pack_color', 'pack_vertex' }, limit = 200,
  on_exception = function(info) verify.record('seed', DC.seed); verify.record('calls', d.records)
    verify.record('exception', info); verify.finish('crash') end }
verify.on_exec('done', function()
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
  verify.record('gpu', log)
end)
_G.ch14_keep = { keep, d.keep }
