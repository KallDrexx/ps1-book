-- Chapter 34 probe (main disc, alt disc). Observes; boots from the disc image. checks.py defines PARAMS (via the file named by CH34_PARAMS):
--   { poses = { {x=, y=, z=, yaw=}, ... }, box = { min = {x,y,z}, max = {x,y,z} } or nil }
-- The program is driven by frame_no (frames completed), because a CD boot takes ~350 emulated frames before main:
--   n == 3        "info": statuses, the Track struct (12 words), proj_h, game_state, wire_mode, camera; patches cam_min / cam_max when PARAMS.box is set
--   n == 5        title snapshot
--   n == 6..8     START held (title -> game)
--   n == 12       "game" snapshot + screenshot (wire_mode 0)
--   n == 14..34   SELECT held 20 frames (wire_mode must become 1 once); "trace" rows {n, game_state, wire_mode} for n in 12..60
--   n == 38       "wire" snapshot + screenshot
--   n == 40..42   SELECT held 2 frames (back to 0); n == 46 snapshot
--   n == 50..60   UP + RIGHT held: "fly" rows {n, eye, yaw}
--   n >= 70       the poses: PARAMS.poses[k] is written to cam_eye / cam_yaw at the end of a frame and recorded in the next one:
--                 { k, eye, yaw, game_state, view = {8 words}, stats = {8 words}, prims, dropped, draw_cycles, frame_cycles,
--                   v = flat list (state, rx, ry, rz, sxy, sz) per vertex, pk = flat list (slot, len, words...) per packet }.
--                 Poses with a wire flag are run with wire_mode set (written together with the pose). Screenshots "s<k>".
if not PARAMS and os.getenv('CH34_PARAMS') then dofile(os.getenv('CH34_PARAMS')) end
local poses = (PARAMS and PARAMS.poses) or {}
local FRAME_SZ = (PARAMS and PARAMS.frame_sz) or (64 * 4 + 32768 + 16)     -- OtFrame: ot[64] + prim[PRIM_BUF_SIZE] + guard[16]

local function s32(a) return verify.s32(a) end
local function s16(a) local v = verify.u16(a); return v >= 32768 and v - 65536 or v end

local out = { scenarios = {}, trace = {}, fly = {}, snaps = {} }
for k, v in pairs(out) do verify.record(k, v) end

PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
  local cp0 = PCSX.getRegisters().CP0.r
  local code = math.floor((tonumber(cp0[13]) or 0) / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = (tonumber(cp0[14]) or 0) % 4294967296, badvaddr = (tonumber(cp0[8]) or 0) % 4294967296 })
  verify.finish('exception')
  return false
end)

-- the packets of the table DrawOTag is given: (slot, tag length, words after the tag)*
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

-- CPU cycles spent inside track_draw (entry to return)
local t0, draw_cycles, ra_bp = 0, 0, nil
if verify.sym.track_draw then
  verify.on_exec('track_draw', function(r)
    t0 = verify.cycles()
    if not ra_bp then ra_bp = verify.on_exec(r.ra, function() draw_cycles = verify.cycles() - t0 end) end
  end)
end

local function eye()
  local b = verify.resolve('cam_eye')
  return { s32(b), s32(b + 4), s32(b + 8) }
end

local function snap(name)
  local st = verify.resolve('track_stats')
  local stats = {}
  for i = 0, 7 do stats[#stats + 1] = s32(st + 4 * i) end
  out.snaps[#out.snaps + 1] = { name = name, game_state = s32('game_state'), state_changes = s32('state_changes'), wire_mode = s32('wire_mode'),
                                prims = s32('prims_submitted'), dropped = s32('prims_dropped'), stats = stats, frame_no = s32('frame_no'),
                                eye = eye(), yaw = s32('cam_yaw'), draw_cycles = draw_cycles }
end

local function info()
  local tr = verify.resolve('track')
  local words = {}
  for i = 0, 11 do words[#words + 1] = verify.u32(tr + 4 * i) end
  verify.record('info', { load_status = s32('load_status'), track_status = s32('track_status'), scene_status = s32('scene_status'), object_count = s32('object_count'),
                          proj_h = s32('proj_h'), game_state = s32('game_state'), wire_mode = s32('wire_mode'), track = words, eye = eye(), yaw = s32('cam_yaw'),
                          box = { s32('cam_min'), s32('cam_min+4'), s32('cam_min+8'), s32('cam_max'), s32('cam_max+4'), s32('cam_max+8') } })
  if PARAMS and PARAMS.box then
    local b = verify.resolve('cam_min')
    for i = 1, 3 do verify.write_u32(b + 4 * (i - 1), PARAMS.box.min[i] % 4294967296) end
    b = verify.resolve('cam_max')
    for i = 1, 3 do verify.write_u32(b + 4 * (i - 1), PARAMS.box.max[i] % 4294967296) end
  end
end

local function record_pose(k, n, frame_cycles)
  local nv = s32(verify.resolve('track') + 20)
  local v = {}
  local rb, xb, zb, sb = verify.resolve('trk_rel'), verify.resolve('trk_sxy'), verify.resolve('trk_sz'), verify.resolve('trk_vstate')
  for i = 0, math.min(math.max(nv, 0), 1024) - 1 do
    local st = verify.u8(sb + i)
    v[#v + 1] = st
    v[#v + 1] = s16(rb + 8 * i)
    v[#v + 1] = s16(rb + 8 * i + 2)
    v[#v + 1] = s16(rb + 8 * i + 4)
    v[#v + 1] = verify.u32(xb + 4 * i)
    v[#v + 1] = s32(zb + 4 * i)
  end
  local vm, vb = {}, verify.resolve('view_mtx')
  for i = 0, 7 do vm[#vm + 1] = verify.u32(vb + 4 * i) end
  local st = verify.resolve('track_stats')
  local stats = {}
  for i = 0, 7 do stats[#stats + 1] = s32(st + 4 * i) end
  out.scenarios[#out.scenarios + 1] = { k = k, eye = eye(), yaw = s32('cam_yaw'), game_state = s32('game_state'), wire_mode = s32('wire_mode'), view = vm, stats = stats,
                                        prims = s32('prims_submitted'), dropped = s32('prims_dropped'), draw_cycles = draw_cycles,
                                        frame_cycles = frame_cycles, v = v, pk = pending, frame_no = n }
  verify.screenshot('s' .. k)
end

local posed, last_cycles = nil, 0
verify.on_exec('frame_done', function()
  local n = s32('frame_no')
  local now = verify.cycles()
  local frame_cycles = now - last_cycles
  last_cycles = now
  if n == 3 then info() end
  if n == 5 then snap('title') end
  if n == 6 then verify.button_down('START') end
  if n == 8 then verify.button_up('START') end
  if n == 12 then snap('game'); verify.screenshot('game') end
  if n == 14 then verify.button_down('SELECT') end
  if n == 34 then verify.button_up('SELECT') end
  if n >= 12 and n <= 60 then out.trace[#out.trace + 1] = { n, s32('game_state'), s32('wire_mode') } end
  if n == 38 then snap('wire'); verify.screenshot('wire') end
  if n == 40 then verify.button_down('SELECT') end
  if n == 42 then verify.button_up('SELECT') end
  if n == 46 then snap('wire_off') end
  if n == 50 then verify.button_down('UP'); verify.button_down('RIGHT') end
  if n == 60 then verify.button_up('UP'); verify.button_up('RIGHT') end
  if n >= 50 and n <= 66 then
    local e = eye()
    out.fly[#out.fly + 1] = { n, e[1], e[2], e[3], s32('cam_yaw') }
  end
  if n >= 70 then
    if posed then record_pose(posed, n, frame_cycles) end
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
