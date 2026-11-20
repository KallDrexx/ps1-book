-- Chapter 17 probe: record, without disturbing the program,
--   * trace[n]    gem_state at the top of every iteration of the frame loop (the `frame` label), before the update;
--   * ev[]        every GP0 E3h (drawing area) and GP1 05h (display start) write: {iteration, vsync frame, kind, value};
--   * samples[]   gem_state + iteration count at every emulated VBlank (just before the program can react to it);
--   * the iteration count at each vsync (frame pacing).
-- The run ends at the harness's max_frames. A runaway (no VBlank wait: thousands of iterations per frame) stops early.
local GP0, GP1 = 0x1F801810, 0x1F801814
local MAX_ITER = 2500
local iter = 0
local trace, ev, samples = {}, {}, {}
local runaway = false

local function state()
  return { verify.s32('gem_state'), verify.s32('gem_state+4'), verify.s32('gem_state+8'), verify.s32('gem_state+12'),
           verify.s32('gem_state+16'), verify.s32('gem_state+20') }
end
local function reg_value(pc)
  local w = verify.u32(pc % 0x200000 + 0x80000000)
  return tonumber(PCSX.getRegisters().GPR.r[bit.band(bit.rshift(w, 16), 31)]) % 4294967296
end
local function stop(why)
  if runaway then return end
  runaway = true
  verify.record('runaway', why)
  verify.finish('runaway: ' .. why)
end

verify.on_exec('frame', function()
  iter = iter + 1
  if iter <= 300 then trace[iter] = state() end
  if iter > MAX_ITER then stop(MAX_ITER .. ' frame-loop iterations: no wait for VBlank?') end
end)

local function on_write(port)
  return function()
    local pc = tonumber(PCSX.getRegisters().pc) % 4294967296
    local ok, v = pcall(reg_value, pc)
    if not ok then return end
    local top = bit.rshift(v, 24)
    if (port == 0 and top == 0xE3) or (port == 1 and top == 0x05) then
      if #ev < 3000 then ev[#ev + 1] = { iter, verify.frame, port, v } end
    end
  end
end
ch17_keep = {
  PCSX.addBreakpoint(GP0, 'Write', 4, 'ch17 gp0', on_write(0)),
  PCSX.addBreakpoint(GP1, 'Write', 4, 'ch17 gp1', on_write(1)),
}

verify.on_vsync(function(f)
  local s = state()
  samples[#samples + 1] = { f, iter, s[1], s[2], s[3], s[4], s[5], s[6] }
  verify.record('trace', trace)
  verify.record('ev', ev)
  verify.record('samples', samples)
  verify.record('iters', iter)
end)
