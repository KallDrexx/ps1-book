-- Chapter 30 probe (main and alt runs). Observes; boots from the disc image. Every time the program calls frame_done() it records
-- one row:  { frame_no, rot.x, rot.y, rot.z, m11 m12 m13 m21 m22 m23 m31 m32 m33, tx ty tz, prims_submitted, load_status, emu_frame, prims }
-- where prims is the flat list of the polygons found by walking the ordering table DrawOTag was given, 23 numbers each:
--   slot, code, r, g, b, x0 y0 u0 v0, x1 y1 u1 v1, x2 y2 u2 v2, x3 y3 u3 v3, clut, tpage     (the POLY_FT4 layout: Appendix / Chapter 30)
-- Once, at the first frame_done(): tim_info (3 x 11 words), tex (3 x 6 halfwords), face_tex (6 bytes), rot_step, cam_z, proj_h.
-- If the generated file before this one defined PATCH = { shots = {frames}, rot = {x,y,z}, rot_step = {x,y,z}, face_tex = {6 bytes} }, those values are
-- written into the program's variables at that first frame_done(). Screenshots are taken inside frame_done() at the frame_no values in SHOTS.
local SHOTS = { [12] = true, [40] = true, [70] = true }
if PATCH and PATCH.shots then
  SHOTS = {}
  for _, n in ipairs(PATCH.shots) do SHOTS[n] = true end
end
local FRAME_SZ = 2320                                   -- OtFrame: ot[64] + prim[2048] + guard[16]

local function s16(a)
  local v = verify.u16(a)
  return v >= 32768 and v - 65536 or v
end

local rows = {}
verify.record('rows', rows)

-- a CPU exception (not an interrupt, not a SYSCALL) ends the run
PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
  local cp0 = PCSX.getRegisters().CP0.r
  local code = math.floor((tonumber(cp0[13]) or 0) / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = (tonumber(cp0[14]) or 0) % 4294967296, badvaddr = (tonumber(cp0[8]) or 0) % 4294967296 })
  verify.finish('exception')
  return false
end)

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
        for k = 0, 3 do
          local a = node + 8 + 8 * k
          prims[#prims + 1] = s16(a)
          prims[#prims + 1] = s16(a + 2)
          prims[#prims + 1] = verify.u8(a + 4)
          prims[#prims + 1] = verify.u8(a + 5)
        end
        prims[#prims + 1] = verify.u16(node + 8 + 6)      -- clut (second half of word 2)
        prims[#prims + 1] = verify.u16(node + 8 + 14)     -- tpage (second half of word 4)
      else
        entry = node
      end
      if nxt == 0xFFFFFF then break end
      node = 0x80000000 + nxt
    end
    pending = prims
  end)
end

local n_calls = 0
verify.on_exec('frame_done', function()
  n_calls = n_calls + 1
  if n_calls == 1 then
    local ti = verify.resolve('tim_info')
    local info = {}
    for i = 0, 32 do info[#info + 1] = verify.u32(ti + 4 * i) end
    verify.record('tim_info', info)
    local tx = verify.resolve('tex')
    local t = {}
    for i = 0, 17 do t[#t + 1] = verify.u16(tx + 2 * i) end
    verify.record('tex', t)
    local ft = verify.resolve('face_tex')
    local f = {}
    for i = 0, 5 do f[#f + 1] = verify.u8(ft + i) end
    verify.record('face_tex', f)
    local rs = verify.resolve('rot_step')
    verify.record('rotstep', { s16(rs), s16(rs + 2), s16(rs + 4) })
    verify.record('cam_z', verify.s32('cam_z'))
    verify.record('proj_h', verify.s32('proj_h'))
    if PATCH then
      local rot, rs2, ft2 = verify.resolve('rot'), verify.resolve('rot_step'), verify.resolve('face_tex')
      for i = 0, 2 do
        if PATCH.rot then verify.write_u16(rot + 2 * i, PATCH.rot[i + 1] % 65536) end
        if PATCH.rot_step then verify.write_u16(rs2 + 2 * i, PATCH.rot_step[i + 1] % 65536) end
      end
      if PATCH.face_tex then for i = 0, 5 do verify.write_u8(ft2 + i, PATCH.face_tex[i + 1]) end end
    end
  end
  local n = verify.s32('frame_no')
  local rot = verify.resolve('rot')
  local row = { n, s16(rot), s16(rot + 2), s16(rot + 4) }
  local m = verify.resolve('mtx')
  for i = 0, 8 do row[#row + 1] = s16(m + 2 * i) end
  for i = 0, 2 do row[#row + 1] = verify.s32(m + 20 + 4 * i) end
  row[#row + 1] = verify.s32('prims_submitted')
  row[#row + 1] = verify.s32('load_status')
  row[#row + 1] = verify.frame
  row[#row + 1] = pending
  pending = {}
  rows[#rows + 1] = row
  if SHOTS[n] then verify.screenshot('f' .. n) end
end)
