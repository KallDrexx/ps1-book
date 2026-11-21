-- Chapter 18 probe.
-- Phase 1 (directcall.lua): expand5 for every 5-bit value, rgb888_to_bgr555 for edge and random colors.
-- Phase 2 (the real program): every entry to rgb888_to_bgr555 is recorded with its argument and its real
-- return value. If the color variable `clear_rgb888` has the sentinel top byte 0x5A, the probe then
-- OVERWRITES $v0 on return with FORCE_BGR555: a program that does not use the routine's result shows the wrong color.
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd32 = DC.rnd32
local FORCE_BGR555 = 0x03E0          -- pure green

local calls = {}
for c5 = 0, 31 do calls[#calls + 1] = { fn = 'expand5', a0 = c5 } end
for _, v in ipairs({ 0, 0xFFFFFF, 0xFF0000, 0x00FF00, 0x0000FF, 0x070707, 0x080808, 0xF8F8F8,
                     0xFFFFFFFF, 0x00FF8040, 0xFF123456, 0x010203 }) do
  calls[#calls + 1] = { fn = 'rgb888_to_bgr555', a0 = v }
end
for _ = 1, 12 do calls[#calls + 1] = { fn = 'rgb888_to_bgr555', a0 = rnd32() } end

local d = DC.new{ calls = calls, routines = { 'expand5', 'rgb888_to_bgr555' }, limit = 2000 }

local entries = {}
local rets = {}
verify.on_exec('rgb888_to_bgr555', function(regs)
  if d.phase ~= 2 then return end
  local r = PCSX.getRegisters().GPR.r
  local ent = { a0 = tonumber(r[4]) % 4294967296 }
  entries[#entries + 1] = ent
  local ra = tonumber(r[31]) % 4294967296
  local sentinel = math.floor(verify.u32('clear_rgb888') / 16777216) == 0x5A
  rets[#rets + 1] = PCSX.addBreakpoint(ra, 'Exec', 4, 'verify ret', function()   -- kept: an unreferenced breakpoint can be collected
    local rr = PCSX.getRegisters().GPR.r
    ent.v0 = tonumber(rr[2]) % 4294967296
    if sentinel then rr[2] = FORCE_BGR555; ent.forced = true end
    return false
  end)
end)

verify.on_exec('stop_here', function()
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
  verify.record('asm_calls', entries)
end)
_G.ch18_keep = { d.keep, rets }
