-- Chapter 27 probe. Observes only; the harness patches the state (poses, path, cam, proj_h) into the .exe before each run.
-- Every time the program calls frame_done() the probe records one row:
--   { frame_no,
--     cube_mtx[64]: per cube m11..m33 (9 s16), tx ty tz (3 s32)            768 values
--     screen_xy[64][8] as s16 pairs (x, y)                                  1024 values
--     screen_z[64][8] (s32)                                                 512 values
--     transform_cycles, render_cycles,                                      CPU cycles between transform_begin()/end(), render_begin()/end()
--     field_cycles[0], field_cycles[1],                                     what the program's own timer reported
--     rtps_n, rtpt_n }                                                      RTPS / RTPT commands executed inside the transform window
-- The first row also records `tables` = { cubes = 640 s32, cam = 3 s32, proj_h, path }.
local N = 64
local function s16(a)
  local v = verify.u16(a)
  return v >= 32768 and v - 65536 or v
end

local rows, calls = {}, 0
verify.record('rows', rows)

local tb, transform_cycles, render_cycles = 0, 0, 0
local rb = 0
local inwin, rtps_n, rtpt_n = false, 0, 0
if verify.sym.transform_begin then
  verify.on_exec('transform_begin', function() tb = verify.cycles(); inwin = true; rtps_n = 0; rtpt_n = 0 end)
end
if verify.sym.transform_end then
  verify.on_exec('transform_end', function() transform_cycles = verify.cycles() - tb; inwin = false end)
end
if verify.sym.render_begin then verify.on_exec('render_begin', function() rb = verify.cycles() end) end
if verify.sym.render_end then verify.on_exec('render_end', function() render_cycles = verify.cycles() - rb end) end

-- Count the GTE commands the program really executes: find every RTPS / RTPT instruction in the program's text once it is
-- loaded (opcode 010010 1, function 0x01 / 0x30) and put an execution breakpoint on it.
local armed = false
local function arm()
  armed = true
  local base = 0x80010000
  for a = base, base + 0x30000, 4 do
    local w = verify.u32(a)
    if bit.rshift(w, 25) == 0x25 then
      local f = bit.band(w, 0x3F)
      if f == 0x01 then verify.on_exec(a, function() if inwin then rtps_n = rtps_n + 1 end end)
      elseif f == 0x30 then verify.on_exec(a, function() if inwin then rtpt_n = rtpt_n + 1 end end) end
    end
  end
end

verify.on_exec('frame_done', function()
  if not armed then arm() end
  calls = calls + 1
  local n = verify.s32('frame_no')
  local row = { n }
  local m = verify.resolve('cube_mtx')
  for c = 0, N - 1 do
    local b = m + 32 * c
    for i = 0, 8 do row[#row + 1] = s16(b + 2 * i) end
    for i = 0, 2 do row[#row + 1] = verify.s32(b + 20 + 4 * i) end
  end
  local sxy, sz = verify.resolve('screen_xy'), verify.resolve('screen_z')
  for i = 0, N * 16 - 1 do row[#row + 1] = s16(sxy + 2 * i) end
  for i = 0, N * 8 - 1 do row[#row + 1] = verify.s32(sz + 4 * i) end
  row[#row + 1] = transform_cycles
  row[#row + 1] = render_cycles
  local fc = verify.resolve('field_cycles')
  row[#row + 1] = verify.s32(fc)
  row[#row + 1] = verify.s32(fc + 4)
  row[#row + 1] = rtps_n
  row[#row + 1] = rtpt_n
  rows[#rows + 1] = row
  if calls == 1 then
    local cubes, cam = {}, {}
    local cu, ca = verify.resolve('cubes'), verify.resolve('cam')
    for i = 0, N * 10 - 1 do cubes[#cubes + 1] = verify.s32(cu + 4 * i) end
    for i = 0, 2 do cam[#cam + 1] = verify.s32(ca + 4 * i) end
    verify.record('tables', { cubes = cubes, cam = cam, proj_h = verify.s32('proj_h'), path = verify.s32('path') })
  end
end)
