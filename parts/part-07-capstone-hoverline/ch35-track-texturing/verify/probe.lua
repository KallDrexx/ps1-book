-- Chapter 35 probe (main disc, alt disc). Observes; boots from the disc image. checks.py writes PARAMS (the file named by CH35_PARAMS):
--   { poses = { {x=, y=, z=, yaw=, wire=}, ... }, frame_sz = n, layout_bytes = n }
-- The program is driven by frame_no (frames completed): a CD boot takes ~350 emulated frames before main.
--   n == 3        "info": statuses (load_status, tex_status, track_tex_count), the Track struct, the bytes of vram_layout and track_tex
--   n == 6..8     START held (title -> game)
--   n >= 12       the poses: PARAMS.poses[k] is written to cam_eye / cam_yaw / wire_mode at the end of a frame and recorded in the next one:
--                 { k, eye, yaw, game_state, wire_mode, view = {8 words}, stats = {8 words}, prims, dropped, pk = flat list (slot, len, words...) per packet }
--                 and a screenshot "s<k>". After the last pose: the guard bytes of both primitive buffers; the run ends (the VRAM is dumped).
if not PARAMS and os.getenv('CH35_PARAMS') then dofile(os.getenv('CH35_PARAMS')) end
local poses = (PARAMS and PARAMS.poses) or {}
local FRAME_SZ = (PARAMS and PARAMS.frame_sz) or (64 * 4 + 32768 + 16)     -- OtFrame: ot[64] + prim[PRIM_BUF_SIZE] + guard[16]

local function s32(a) return verify.s32(a) end

local out = { scenarios = {} }
verify.record('scenarios', out.scenarios)

PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
  local cp0 = PCSX.getRegisters().CP0.r
  local code = math.floor((tonumber(cp0[13]) or 0) / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = (tonumber(cp0[14]) or 0) % 4294967296, badvaddr = (tonumber(cp0[8]) or 0) % 4294967296 })
  verify.finish('exception')
  return false
end)

-- the packets of the ordering table DrawOTag is given: (slot, tag length, words after the tag)*
local pending = {}
if verify.sym.DrawOTag and verify.sym.ot_frames then
  verify.on_exec('DrawOTag', function(r)
    local base = verify.resolve('ot_frames')
    local node, prims, entry, n = r.a0, {}, 0, 0
    while n < 6000 do
      local w = verify.u32(node)
      local len, nxt = bit.rshift(w, 24), bit.band(w, 0xFFFFFF)
      n = n + 1
      if len > 0 then
        prims[#prims + 1] = math.floor(((entry - base) % FRAME_SZ) / 4)
        prims[#prims + 1] = len
        for k = 1, len do prims[#prims + 1] = verify.u32(node + 4 * k) end
      else
        entry = node
      end
      if nxt == 0xFFFFFF then break end
      node = 0x80000000 + nxt
    end
    pending = prims
  end)
end

local function eye()
  local b = verify.resolve('cam_eye')
  return { s32(b), s32(b + 4), s32(b + 8) }
end

local function hex(addr, n)
  local raw, t = verify.read_bytes(addr, n), {}
  for i = 1, n do t[i] = string.format('%02x', raw:byte(i)) end
  return table.concat(t)
end

local function info()
  local tr = verify.resolve('track')
  local words = {}
  for i = 0, 11 do words[#words + 1] = verify.u32(tr + 4 * i) end
  local n = (PARAMS and PARAMS.layout_bytes) or 96
  verify.record('info', { load_status = s32('load_status'), track_status = s32('track_status'), tex_status = s32('tex_status'),
                          tex_count = s32('track_tex_count'), game_state = s32('game_state'), track = words,
                          layout = hex(verify.resolve('vram_layout'), n), tex = hex(verify.resolve('track_tex'), n) })
end

local function record_pose(k, n)
  local vm, vb = {}, verify.resolve('view_mtx')
  for i = 0, 7 do vm[#vm + 1] = verify.u32(vb + 4 * i) end
  local st = verify.resolve('track_stats')
  local stats = {}
  for i = 0, 7 do stats[#stats + 1] = s32(st + 4 * i) end
  out.scenarios[#out.scenarios + 1] = { k = k, eye = eye(), yaw = s32('cam_yaw'), game_state = s32('game_state'), wire_mode = s32('wire_mode'), view = vm,
                                        stats = stats, prims = s32('prims_submitted'), dropped = s32('prims_dropped'), pk = pending, frame_no = n }
  verify.screenshot('s' .. k)
end

local posed = nil
verify.on_exec('frame_done', function()
  local n = s32('frame_no')
  if n == 3 then info() end
  if n == 6 then verify.button_down('START') end
  if n == 8 then verify.button_up('START') end
  if n >= 12 then
    if posed then record_pose(posed, n) end
    local nxt = (posed or 0) + 1
    local c = poses[nxt]
    if c then
      local b = verify.resolve('cam_eye')
      verify.write_u32(b, c.x % 4294967296); verify.write_u32(b + 4, c.y % 4294967296); verify.write_u32(b + 8, c.z % 4294967296)
      verify.write_u32('cam_yaw', c.yaw % 4096)
      verify.write_u32('wire_mode', c.wire or 0)
      posed = nxt
    else
      local base, g = verify.resolve('ot_frames'), {}
      for f = 0, 1 do
        local raw, t = verify.read_bytes(base + f * FRAME_SZ + FRAME_SZ - 16, 16), {}
        for i = 1, 16 do t[i] = raw:byte(i) end
        g[#g + 1] = t
      end
      verify.record('guards', g)
      verify.collect('done')
    end
  end
end)
