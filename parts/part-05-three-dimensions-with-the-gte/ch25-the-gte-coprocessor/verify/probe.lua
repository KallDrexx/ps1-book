-- Chapter 25 probe. Observes only; the harness patches the state (start angles, steps, colours, cam_z, proj_h, cube)
-- into the .exe before each run, and ends the run at max_frames. Every time the program calls frame_done() the probe
-- records one row:
--   { frame_no, rot.x, rot.y, rot.z,                       3 angles
--     m11 m12 m13 m21 m22 m23 m31 m32 m33, tx ty tz,       mtx (12 values)
--     x0 y0 ... x7 y7,                                     screen_xy[] (16 s16)
--     z0 ... z7,                                           screen_z[] (8 s32)
--     gte_flags, prims_submitted, faces_drawn, face_mask,
--     render_cycles,                                       CPU cycles from render_begin() to render_end()
--     prims }                                              the quads found by WALKING the ordering table the program
--                                                          handed to DrawOTag this frame: flat list
--                                                          { slot, code, r, g, b, x0, y0, x1, y1, x2, y2, x3, y3, ... }
-- The first row of a run also records `tables` = { faces = 24 u8, colors = 18 u8, cube = 32 s16, cam_z, proj_h, step = 3 s16 }.
-- Screenshots are taken inside frame_done() at the frame_no values in SHOTS (the picture the program has just finished).
local SHOTS = { [2] = true, [30] = true, [95] = true }
local FRAME_SZ = 2320                                   -- OtFrame: ot[64] + prim[2048] + guard[16]

local function s16(a)
  local v = verify.u16(a)
  return v >= 32768 and v - 65536 or v
end

local rows, calls = {}, 0
verify.record('rows', rows)

-- cycles between render_begin() and render_end()
local t0, render_cycles = 0, 0
if verify.sym.render_begin then verify.on_exec('render_begin', function() t0 = verify.cycles() end) end
if verify.sym.render_end then verify.on_exec('render_end', function() render_cycles = verify.cycles() - t0 end) end

-- walk the list DrawOTag is given, exactly as the GPU's DMA would
local pending = {}
if verify.sym.DrawOTag and verify.sym.ot_frames then
  verify.on_exec('DrawOTag', function(r)
    local base = verify.resolve('ot_frames')
    local node, prims, entry, n = r.a0, {}, 0, 0
    while n < 400 do
      local w = verify.u32(node)
      local len, nxt = bit.rshift(w, 24), bit.band(w, 0xFFFFFF)
      n = n + 1
      if len > 0 then
        local c = verify.u32(node + 4)
        prims[#prims + 1] = math.floor(((entry - base) % FRAME_SZ) / 4)
        prims[#prims + 1] = bit.rshift(c, 24)
        prims[#prims + 1] = bit.band(c, 255)
        prims[#prims + 1] = bit.band(bit.rshift(c, 8), 255)
        prims[#prims + 1] = bit.band(bit.rshift(c, 16), 255)
        for k = 0, 7 do prims[#prims + 1] = s16(node + 8 + 2 * k) end
      else
        entry = node
      end
      if nxt == 0xFFFFFF then break end
      node = 0x80000000 + nxt
    end
    pending = prims
  end)
end

verify.on_exec('frame_done', function()
  calls = calls + 1
  local n = verify.s32('frame_no')
  local row = { n, s16(verify.resolve('rot')), s16(verify.resolve('rot') + 2), s16(verify.resolve('rot') + 4) }
  local m = verify.resolve('mtx')
  for i = 0, 8 do row[#row + 1] = s16(m + 2 * i) end
  for i = 0, 2 do row[#row + 1] = verify.s32(m + 20 + 4 * i) end
  local sxy, sz = verify.resolve('screen_xy'), verify.resolve('screen_z')
  for i = 0, 15 do row[#row + 1] = s16(sxy + 2 * i) end
  for i = 0, 7 do row[#row + 1] = verify.s32(sz + 4 * i) end
  row[#row + 1] = verify.s32('gte_flags')
  row[#row + 1] = verify.s32('prims_submitted')
  row[#row + 1] = verify.s32('faces_drawn')
  row[#row + 1] = verify.s32('face_mask')
  row[#row + 1] = render_cycles
  row[#row + 1] = pending
  pending = {}
  rows[#rows + 1] = row
  if calls == 1 then
    local faces, colors, cube, step = {}, {}, {}, {}
    local fa, co, cu, st = verify.resolve('faces'), verify.resolve('face_colors'), verify.resolve('cube'), verify.resolve('rot_step')
    for i = 0, 23 do faces[#faces + 1] = verify.u8(fa + i) end
    for i = 0, 17 do colors[#colors + 1] = verify.u8(co + i) end
    for i = 0, 31 do cube[#cube + 1] = s16(cu + 2 * i) end
    for i = 0, 2 do step[#step + 1] = s16(st + 2 * i) end
    verify.record('tables', { faces = faces, colors = colors, cube = cube, cam_z = verify.s32('cam_z'),
                              proj_h = verify.s32('proj_h'), step = step })
  end
  if SHOTS[n] then verify.screenshot('f' .. n) end
end)
