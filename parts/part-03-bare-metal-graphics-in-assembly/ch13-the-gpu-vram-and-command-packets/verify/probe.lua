-- Chapter 13 probe.
-- Phase 1: calls gpu_init, gpu_clear and gpu_rect DIRECTLY (tools/verify-lib/directcall.lua) with sentinel-seeded
-- callee-saved registers, garbage temporaries and the 5th argument (h) at 16($sp) with decoys around it.
-- Around every call it records
--   * the GPU transcript: every word written to GP0 (0x1F801810) and GP1 (0x1F801814), in order, and how many
--     GPUSTAT reads (lw from 0x1F801814) happened before the first GP0 word;
--   * a VRAM diff: bounding box, count and distinct raw values of every pixel the call changed (whole 1024x512).
-- Phase 2: the real driver runs to `done`; its whole transcript is recorded.
-- Breakpoints on the GPU ports work in the interpreter. The value of a write is the source register of the `sw`
-- at the faulting pc (decoded here), because the breakpoint callback does not get it.
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd, rnd32, SP = DC.rnd, DC.rnd32, DC.SP
local ffi = require('ffi')
local GP0, GP1 = 0x1F801810, 0x1F801814

-- ---- transcript -----------------------------------------------------------------------------
local log, reads, cap = {}, 0, 0
local first_gp0_reads = nil
local function new_log() log, reads, first_gp0_reads = {}, 0, nil end
local function reg_value(pc)
  local w = verify.u32(pc % 0x200000 + 0x80000000)
  local op, rt = bit.rshift(w, 26), bit.band(bit.rshift(w, 16), 31)
  return DC.regget(rt), op
end
local function on_write(port)
  return function(addr, width)
    local pc = tonumber(PCSX.getRegisters().pc) % 4294967296
    local ok, v, op = pcall(reg_value, pc)
    if #log < 3000 then log[#log + 1] = { port, ok and v or -1, ok and op or -1 } end
    if port == 0 and not first_gp0_reads then first_gp0_reads = reads end
  end
end
local keep = {
  PCSX.addBreakpoint(GP0, 'Write', 4, 'ch13 gp0', on_write(0)),
  PCSX.addBreakpoint(GP1, 'Write', 4, 'ch13 gp1', on_write(1)),
  PCSX.addBreakpoint(GP1, 'Read', 4, 'ch13 stat', function() reads = reads + 1 end),
}

-- ---- VRAM diff --------------------------------------------------------------------------------
local N = 1024 * 512
local before = ffi.new('uint16_t[?]', N)
local function vram_ptr() return ffi.cast('const uint16_t*', PCSX.GPU.getVRAM().data) end
local function snapshot() ffi.copy(before, vram_ptr(), N * 2) end
local function diff()
  local p = vram_ptr()
  local x0, y0, x1, y1, n, vals, nv = 1e9, 1e9, -1, -1, 0, {}, 0
  for y = 0, 511 do
    local row = y * 1024
    for x = 0, 1023 do
      local a = p[row + x]
      if a ~= before[row + x] then
        n = n + 1
        if x < x0 then x0 = x end
        if x > x1 then x1 = x end
        if y < y0 then y0 = y end
        if y > y1 then y1 = y end
        if nv < 6 and not vals[a] then vals[a] = true; nv = nv + 1 end
      end
    end
  end
  local list = {}
  for v in pairs(vals) do list[#list + 1] = v end
  table.sort(list)
  return { x0 = x0, y0 = y0, x1 = x1, y1 = y1, n = n, vals = list }
end

-- ---- the calls ---------------------------------------------------------------------------------
local used = {}
local function color()                       -- distinct 15-bit colours, never black, random garbage in bits 31-24
  while true do
    local r, g, b = rnd(256), rnd(256), rnd(256)
    local c555 = bit.rshift(r, 3) + bit.lshift(bit.rshift(g, 3), 5) + bit.lshift(bit.rshift(b, 3), 10)
    if c555 ~= 0 and not used[c555] then
      used[c555] = true
      return bit.lshift(r, 16) + bit.lshift(g, 8) + b + (rnd(2) == 0 and 0 or bit.lshift(rnd(256), 24))
    end
  end
end

local calls = {}
local function add(c)
  c.limit = 400
  c.prepare = function(cc)
    new_log()
    snapshot()
    verify.write_u32(SP + 0, 0xBAD00000); verify.write_u32(SP + 4, 0xBAD00004)
    verify.write_u32(SP + 8, 0xBAD00008); verify.write_u32(SP + 12, 0xBAD0000C)
    verify.write_u32(SP + 16, cc.h or 0)
    for i = 20, 44, 4 do verify.write_u32(SP + i, 0xBADBAD00 + i) end
  end
  c.check = function(cc, rec)
    rec.log = log
    rec.reads_before_gp0 = first_gp0_reads or -1
    rec.gpustat_reads = reads
    rec.diff = diff()
    new_log()
  end
  calls[#calls + 1] = c
end
local function clear(x, y, w, h) add({ fn = 'gpu_clear', a0 = color(), a1 = x, a2 = y, a3 = w, h = h }) end
local function rect(x, y, w, h)  add({ fn = 'gpu_rect',  a0 = color(), a1 = x, a2 = y, a3 = w, h = h }) end

add({ fn = 'gpu_init' })
-- fill rectangle: outside the 320x240 drawing area (fill ignores it), x a multiple of 16
clear(512, 256, 64, 32)                      -- exact multiples
clear(16 * (20 + rnd(20)), 250 + rnd(100), 16 * (1 + rnd(6)), 1 + rnd(40))
clear(16 * (4 + rnd(40)), 260 + rnd(150), 20, 5)       -- w = 20 is rounded up to 32
clear(640, 300, 1, 3)                        -- w = 1 is rounded up to 16
clear(336, 300, 17, 3)                       -- w = 17 is rounded up to 32
clear(0, 400, 320, 100)                      -- big, aligned
clear(16 * rnd(60), 300 + rnd(100), 16 * (1 + rnd(5)), 1 + rnd(30))
-- monochrome rectangle: inside the drawing area, any x, y, w, h
rect(0, 0, 40, 24)
rect(1 + rnd(250), 1 + rnd(150), 1 + rnd(60), 1 + rnd(60))
rect(7, 9, 1, 1)
rect(40 * rnd(8), 24, 40, 192)
rect(33 + rnd(100), 1 + rnd(200), 17 + rnd(30), 3 + rnd(30))
-- the drawing area (set by gpu_init) clips it
rect(300, 100, 40, 20)                       -- half outside on the right
rect(10, 230, 30, 30)                        -- half outside at the bottom
rect(330, 50, 40, 40)                        -- completely outside (right of the area)
rect(50, 245, 30, 10)                        -- completely outside (below the area)

-- phase 2 transcript of the real driver (the harness's own direct calls are over by then)
local d
local p2 = { log = {}, reads = 0 }
d = DC.new{ calls = calls, routines = { 'gpu_init', 'gpu_clear', 'gpu_rect' }, limit = 400,
  on_exception = function(info) p2.crash = info; verify.record('phase2', p2); verify.record('seed', DC.seed)
    verify.record('calls', d.records); verify.record('exception', info); verify.finish('crash') end }
verify.on_exec('done', function()
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
  p2.log = log; p2.reads = reads; p2.first_gp0_reads = first_gp0_reads
  verify.record('phase2', p2)
end)
_G.ch13_keep = { keep, d.keep }
