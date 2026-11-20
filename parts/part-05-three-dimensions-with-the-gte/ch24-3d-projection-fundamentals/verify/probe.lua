-- Chapter 24 probe. Observes only; the harness patches the state (cube table, steps, start angles, cam_z, proj_h)
-- into the .exe before the run. Every time the program calls frame_done() the probe records one row:
--   {frame_no, angle_x, angle_y, p0x, p0y, ... p7x, p7y}      (projected[] as signed 16-bit)
-- The first row also carries the tables and the lens state:
--   tables = {cube = {24 s16}, edges = {24 u8}, cam_z, proj_h, step_x, step_y}
-- Screenshots are taken inside frame_done() at the frame_no values in SHOTS, so the
-- picture is the one the program has just finished (DrawOTag was waited for by display_swap).
local N = 120                                  -- frames to observe
local SHOTS = { [30] = true, [95] = true }       -- frame_no values at which to take a screenshot

local function s16(a)
  local v = verify.u16(a)
  return v >= 32768 and v - 65536 or v
end

local rows, calls = {}, 0
verify.record('rows', rows)

verify.on_exec('frame_done', function()
  calls = calls + 1
  local n = verify.s32('frame_no')
  local row = { n, verify.s32('angle_x'), verify.s32('angle_y') }
  for i = 0, 15 do row[#row + 1] = s16(verify.resolve('projected') + 2 * i) end
  rows[#rows + 1] = row
  if calls == 1 then
    local cube, edges = {}, {}
    for i = 0, 23 do cube[#cube + 1] = s16(verify.resolve('cube') + 2 * i) end
    for i = 0, 23 do edges[#edges + 1] = verify.u8(verify.resolve('edges') + i) end
    verify.record('tables', { cube = cube, edges = edges, cam_z = verify.s32('cam_z'), proj_h = verify.s32('proj_h'),
                              step_x = verify.s32('step_x'), step_y = verify.s32('step_y') })
  end
  if SHOTS[n] then verify.screenshot('f' .. n) end
  if n >= N then
    verify.record('calls', calls)
    verify.finish('done')
  end
end)
