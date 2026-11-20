-- Chapter 29 probe (the main run). Observes only; boots from the disc image. Every time the program calls
-- frame_done() it records one row:
--   { frame_no, rot.x, rot.y, rot.z, m11 m12 m13 m21 m22 m23 m31 m32 m33, tx ty tz, prims_submitted, load_status, emu_frame }
-- plus, walking the ordering table DrawOTag was given, the polygons it holds:
--   prims = flat list { slot, code, r, g, b, x0, y0, x1, y1, x2, y2 [, x3, y3] } (code 0x20 = F3, 0x28 = F4)
-- Once, at the first frame_done(): `info` (model_info), the pointer/size of the buffer cd_load_file returned and its first
-- bytes. During the whole run: how many times the CD library entry points were called (`calls`), and how many times the
-- CD controller's registers (0x1F801800..03) were written. A CPU exception ends the run.
-- Screenshots are taken inside frame_done() at the frame_no values in SHOTS.
local SHOTS = { [12] = true, [70] = true }
local FRAME_SZ = 2320                                   -- OtFrame: ot[64] + prim[2048] + guard[16]
local DUMP_MAX = 4096

local function s16(a)
  local v = verify.u16(a)
  return v >= 32768 and v - 65536 or v
end

local rows, calls, tables = {}, {}, {}
verify.record('rows', rows)
verify.record('calls', calls)

for _, name in ipairs({ 'cd_init', 'cd_load_file', 'model_parse', 'CdInit', 'CdSearchFile', 'CdControl', 'CdControlB', 'CdRead',
                        'CdReadRetry', 'CdReadSync', 'malloc' }) do
  if verify.sym[name] then
    calls[name] = 0
    verify.on_exec(name, function() calls[name] = calls[name] + 1 end)
  end
end

local cd_writes = 0
verify.record('cd_reg_writes', 0)
local ok = pcall(function()
  verify.on_access('Write', 0x1F801800, 4, function() cd_writes = cd_writes + 1; verify.record('cd_reg_writes', cd_writes) end)
end)

-- a CPU exception (not an interrupt, not a SYSCALL) ends the run
PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
  local cp0 = PCSX.getRegisters().CP0.r
  local code = math.floor((tonumber(cp0[13]) or 0) / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = (tonumber(cp0[14]) or 0) % 4294967296, badvaddr = (tonumber(cp0[8]) or 0) % 4294967296 })
  verify.finish('exception')
  return false
end)

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
        local npts = (bit.rshift(c, 24) == 0x28) and 4 or 3
        for k = 0, 2 * npts - 1 do prims[#prims + 1] = s16(node + 8 + 2 * k) end
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
  if n_calls == 1 then
    local mi = verify.resolve('model_info')
    local info = { verify.s32(mi), verify.s32(mi + 4) }
    for k = 0, 5 do info[#info + 1] = s16(mi + 8 + 2 * k) end
    verify.record('info', info)
    local buf, size = verify.u32('model_buf'), verify.u32('model_size')
    verify.record('buf', buf)
    verify.record('size', size)
    verify.record('rotstep', { s16(verify.resolve('rot_step')), s16(verify.resolve('rot_step') + 2), s16(verify.resolve('rot_step') + 4) })
    verify.record('cam_z', verify.s32('cam_z'))
    verify.record('proj_h', verify.s32('proj_h'))
    if buf ~= 0 and size > 0 and size <= DUMP_MAX then
      local bytes = {}
      for i = 0, size - 1 do bytes[#bytes + 1] = verify.u8(buf + i) end
      verify.record('bytes', bytes)
    end
  end
  if SHOTS[n] then verify.screenshot('f' .. n) end
end)
