-- Chapter 15 probe.
-- Phase 1: draw_flat_tri, draw_flat_quad and draw_gouraud_tri are called DIRECTLY (tools/verify-lib/directcall.lua).
--   Arguments 0-3 go in $a0-$a3; arguments 4.. are written at 16($sp), 20($sp), ... with junk in the home area
--   (0..15($sp)) and above the arguments, so a routine that reads the wrong offset gets garbage.
--   Every GP0/GP1 write made during a call is stored with the call's record (rec.words), together with the number of
--   GPUSTAT reads (lw from 0x1F801814) before it and at the start of the call (rec.r0).
-- Phase 2: the real program runs to `done`. Every GP0/GP1 write is logged the same way (record 'gpu'), and the
--   probe counts how often each routine is entered (record 'entries').
-- The value of a write is the source register of the `sw` at the faulting pc (decoded here), because the breakpoint
-- callback does not get it.
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd, rnd32 = DC.rnd, DC.rnd32
local SP = DC.SP
local GP0, GP1 = 0x1F801810, 0x1F801814

local d
local log1, log2, reads, reads2 = {}, {}, 0, 0
-- The real run sends a few hundred GP0 words and reads GPUSTAT about once per packet. Far more means a runaway
-- (a routine that lost $ra loops back into itself, or a wait that can never end): stop at once instead of
-- crawling to the frame limit or the 20 s hard timeout. Results are recorded up front (by reference), so the
-- phase-1 records survive any early end.
local MAX_WORDS2, MAX_READS2 = 5000, 50000
local function runaway(why)
  verify.record('runaway', why)
  verify.finish('runaway: ' .. why)
end
local function reg_value(pc)
  local w = verify.u32(pc % 0x200000 + 0x80000000)
  local op, rt = bit.rshift(w, 26), bit.band(bit.rshift(w, 16), 31)
  return DC.regget(rt), op
end
local function on_write(port)
  return function(addr, width)
    local pc = tonumber(PCSX.getRegisters().pc) % 4294967296
    local ok, v, op = pcall(reg_value, pc)
    local lg = (d and d.phase == 1) and log1 or log2
    if #lg < 20000 then lg[#lg + 1] = { port, ok and v or -1, ok and op or -1, reads } end
    if lg == log2 and #log2 > MAX_WORDS2 then runaway(MAX_WORDS2 .. ' GPU words written without reaching done') end
  end
end
local keep = {
  PCSX.addBreakpoint(GP0, 'Write', 4, 'ch15 gp0', on_write(0)),
  PCSX.addBreakpoint(GP1, 'Write', 4, 'ch15 gp1', on_write(1)),
  PCSX.addBreakpoint(GP1, 'Read', 4, 'ch15 stat', function()
    reads = reads + 1
    if d and d.phase == 2 then
      reads2 = reads2 + 1
      if reads2 > MAX_READS2 then runaway(MAX_READS2 .. ' GPUSTAT reads without reaching done: a wait that never ends') end
    end
  end),
}

local function u32(v) return v % 4294967296 end
local function s11() return rnd(2048) - 1024 end
local calls = {}
-- args: list of 32-bit values; the first four go in registers, the rest on the stack
local function add(fn, args)
  local c = { fn = fn, limit = 600, args = {} }
  for i, v in ipairs(args) do c.args[i] = u32(v) end
  for i = 1, math.min(4, #args) do c['a' .. (i - 1)] = u32(args[i]) end
  c.nargs = #args
  c.prepare = function(cc)
    cc.m0, cc.r0 = #log1, reads
    for i = 0, 12, 4 do verify.write_u32(SP + i, 0xBAD00000 + i) end              -- home area: junk
    for i = 4, #cc.args - 1 do verify.write_u32(SP + 4 * i, cc.args[i + 1]) end           -- argument i (0-based) at 4*i($sp)
    for i = 4 * #cc.args, 4 * #cc.args + 48, 4 do verify.write_u32(SP + i, 0xBADBAD00 + i) end  -- above: junk
  end
  c.check = function(cc, rec)
    local w = {}
    for i = cc.m0 + 1, #log1 do w[#w + 1] = log1[i] end
    rec.words = w
  end
  calls[#calls + 1] = c
end
local function col() return rnd32() end
local function rgb() return rnd(0x1000000) end

add('draw_flat_tri', { 0xFFA000, -90, -100, -30, -20, -150, -20 })
add('draw_flat_tri', { 0xAB123456, 5, 6, 7, 8, 9, 10 })
add('draw_flat_tri', { 0x00FF8001, -1, -1, 319, 239, 0, 239 })
for _ = 1, 5 do add('draw_flat_tri', { col(), s11(), s11(), s11(), s11(), s11(), s11() }) end

add('draw_flat_quad', { 0x20C0A0, 30, -100, 140, -90, 20, -20, 130, -15 })
add('draw_flat_quad', { 0xFF010203, -1, -2, -3, -4, -5, -6, -7, -8 })
add('draw_flat_quad', { 0x00FF8001, 0, 0, 319, 0, 0, 239, 319, 239 })
for _ = 1, 5 do add('draw_flat_quad', { col(), s11(), s11(), s11(), s11(), s11(), s11(), s11(), s11() }) end

add('draw_gouraud_tri', { 0xFF0000, 10, 20, 0x00FF00, 30, 90, 0x0000FF, -50, 95 })
add('draw_gouraud_tri', { 0x01020304, -1, -2, 0x00ABCDEF, 3, 4, 0xFF123456, -5, -6 })
add('draw_gouraud_tri', { 0x00FF8001, 0, 0, 0x00FFFFFF, 319, 0, 0x00000000, 0, 239 })
for _ = 1, 5 do add('draw_gouraud_tri', { col(), s11(), s11(), col(), s11(), s11(), col(), s11(), s11() }) end

local ROUTINES = { 'draw_flat_tri', 'draw_flat_quad', 'draw_gouraud_tri' }
d = DC.new{ calls = calls, routines = ROUTINES, limit = 600,
  on_exception = function(info) verify.record('seed', DC.seed); verify.record('calls', d.records)
    verify.record('exception', info); verify.finish('crash') end }
verify.record('seed', DC.seed)          -- tables are recorded by reference: their final contents are written
verify.record('calls', d.records)       -- whenever the run ends (done, exception, runaway or frame limit)
verify.record('entries', d.entries)
verify.record('gpu', log2)
_G.ch15_keep = { keep, d.keep }
