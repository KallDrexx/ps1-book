-- Chapter 19 probe (does not disturb the program). Records
--   ev[]      every GP1 05h (display start) write: {vsync frame, frame_no, hue, rect_x, hue_step, value,
--             number of display_swap() calls entered so far (0 = a write from display_init)}
--   vs[]      per emulated VBlank: {vsync frame, frame_no, number of 05h writes so far}
-- A runaway (hundreds of display-start writes: no VBlank wait) ends the run early.
local GP1 = 0x1F801814
local MAX_EV = 400
local ev, vs = {}, {}
local runaway = false
local swaps = 0

local function reg_value(pc)
  local w = verify.u32(pc % 0x200000 + 0x80000000)
  return tonumber(PCSX.getRegisters().GPR.r[bit.band(bit.rshift(w, 16), 31)]) % 4294967296
end

local function on_gp1()
  local pc = tonumber(PCSX.getRegisters().pc) % 4294967296
  local ok, v = pcall(reg_value, pc)
  if not ok or bit.rshift(v, 24) ~= 0x05 then return end
  ev[#ev + 1] = { verify.frame, verify.u32('frame_no'), verify.u32('hue'), verify.s32('rect_x'),
                  verify.u32('hue_step'), v, swaps }
  if #ev > MAX_EV and not runaway then
    runaway = true
    verify.record('runaway', MAX_EV .. ' display-start writes: no wait for VBlank?')
    verify.record('ev', ev)
    verify.finish('runaway')
  end
end
ch19_keep = { PCSX.addBreakpoint(GP1, 'Write', 4, 'ch19 gp1', on_gp1) }
verify.on_exec('display_swap', function() swaps = swaps + 1 end)

verify.on_vsync(function(f)
  vs[#vs + 1] = { f, verify.u32('frame_no'), #ev }
  verify.record('ev', ev)
  verify.record('vs', vs)
end)
