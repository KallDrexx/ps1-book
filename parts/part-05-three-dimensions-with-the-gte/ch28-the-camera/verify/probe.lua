-- Chapter 28 probe (observation only). The harness patches the start state and presses the pad buttons (`inputs=`).
-- Every time the program calls frame_done() the probe records one row:
--   { frame_no, vsync_frame,
--     objects[0..2] as 45 s32 (Chapter 26's layout),
--     cam_eye (3 s32), cam_target (3), cam_up (3),
--     view_mtx: 9 s16 (row-major) then t (3 s32),
--     render_cycles,                       CPU cycles from render_begin() to render_end()
--     prims }                              the quads found by WALKING the ordering table handed to DrawOTag:
--                                          flat list { slot, code, r, g, b, x0, y0, x1, y1, x2, y2, x3, y3, ... }
-- The first row of a run also records `tables` = { cube, faces, shade, floor_colors, gravity, floor_y, proj_h, speed,
-- cam_min, cam_max }. Screenshots are taken inside frame_done() at the frame_no values in SHOTS.
local SHOTS = { [3] = true, [60] = true, [100] = true, [140] = true, [180] = true, [215] = true, [260] = true, [295] = true }
local FRAME_SZ = 2320                                   -- OtFrame: ot[64] + prim[2048] + guard[16]
local NFIELDS, NOBJ = 15, 3

local function s16(a)
  local v = verify.u16(a)
  return v >= 32768 and v - 65536 or v
end

local rows, calls = {}, 0
verify.record('rows', rows)

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

-- A CPU fault (not an interrupt or the SDK's syscalls) would leave OpenBIOS halted until the hard timeout: record it, end the run.
local R = PCSX.getRegisters()
keep_exc = PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'ch28 exception', function()
  local cause, epc, bad = 0, 0, 0
  pcall(function()
    local cp0 = R.CP0.r
    cause, epc, bad = tonumber(cp0[13]) or 0, tonumber(cp0[14]) or 0, tonumber(cp0[8]) or 0
  end)
  local code = math.floor(cause / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = epc % 4294967296, badvaddr = bad % 4294967296 })
  verify.finish('exception')
end)

local function vec(sym)
  local a = verify.resolve(sym)
  return { verify.s32(a), verify.s32(a + 4), verify.s32(a + 8) }
end

verify.on_exec('frame_done', function()
  calls = calls + 1
  local n = verify.s32('frame_no')
  local row = { n, verify.frame }
  local o = verify.resolve('objects')
  for i = 0, NFIELDS * NOBJ - 1 do row[#row + 1] = verify.s32(o + 4 * i) end
  for _, s in ipairs({ 'cam_eye', 'cam_target', 'cam_up' }) do
    for _, v in ipairs(vec(s)) do row[#row + 1] = v end
  end
  local vm = verify.resolve('view_mtx')
  for i = 0, 8 do row[#row + 1] = s16(vm + 2 * i) end
  for i = 0, 2 do row[#row + 1] = verify.s32(vm + 20 + 4 * i) end
  row[#row + 1] = render_cycles
  row[#row + 1] = pending
  pending = {}
  rows[#rows + 1] = row
  if calls == 1 then
    local cube, faces, shade, fc = {}, {}, {}, {}
    local cu, fa, sh, fo = verify.resolve('cube'), verify.resolve('faces'), verify.resolve('face_shade'), verify.resolve('floor_colors')
    for i = 0, 31 do cube[#cube + 1] = s16(cu + 2 * i) end
    for i = 0, 23 do faces[#faces + 1] = verify.u8(fa + i) end
    for i = 0, 5 do shade[#shade + 1] = verify.u16(sh + 2 * i) end
    for i = 0, 5 do fc[#fc + 1] = verify.u8(fo + i) end
    verify.record('tables', { cube = cube, faces = faces, shade = shade, floor_colors = fc,
                              gravity = verify.s32('gravity'), floor_y = verify.s32('floor_y'), proj_h = verify.s32('proj_h'),
                              speed = verify.s32('cam_speed'), cam_min = vec('cam_min'), cam_max = vec('cam_max') })
  end
  if SHOTS[n] then verify.screenshot('f' .. n) end
end)
