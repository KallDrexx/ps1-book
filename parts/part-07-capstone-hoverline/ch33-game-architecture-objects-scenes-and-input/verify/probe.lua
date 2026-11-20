-- Chapter 33 probe (main run and alt run). Observes; boots from the disc image. checks.py defines PARAMS = { cams = { {x=, y=, z=, yaw=}, ... }, alt = bool }
-- before loading this file. The program is driven by frame_no (the number of frames it has completed), because a CD boot takes ~350
-- emulated frames before main:
--   n == 3   record "info": statuses, camera, shapes, the whole list walked through object_head (node words), store, cull radius
--   n == 5   "title" snapshot (state, counters, visible flags) + screenshot "title"
--   n == 6..26   START held down (20 frames); every frame from 6 to 34 a "trace" row {n, game_state, state_changes}
--   n == 34  "game1" snapshot + screenshot
--   n == 36..48  START held 12 frames (in the game: back to the title ONCE); n == 56 "title2" snapshot + screenshot
--   n == 58..60  START held 2 frames; n == 66 "game2" snapshot
--   n == 68..78  UP + RIGHT + R1 + R2 held; "fly" rows {n, eye, yaw}
--   then the camera scenarios: PARAMS.cams[k] is written to cam_eye / cam_yaw at the end of a frame and recorded in the next one:
--   { k, eye = {x,y,z}, yaw, game_state, submitted = submitted_objects, prims, dropped, visible = {0/1 per node in list order} }, screenshot "s<k>".
if not PARAMS and os.getenv('CH33_PARAMS') then dofile(os.getenv('CH33_PARAMS')) end
local cams = (PARAMS and PARAMS.cams) or {}
local FRAME_SZ = 2320

local function s32(a) return verify.s32(a) end

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

local function walk()
  local nodes, p, guard = {}, verify.u32('object_head'), 0
  while p ~= 0 and guard < 300 do
    local w = {}
    for i = 0, 11 do w[#w + 1] = verify.u32(p + 4 * i) end
    w.addr = p
    nodes[#nodes + 1] = w
    p = w[1]
    guard = guard + 1
  end
  return { nodes = nodes, cyclic = (guard >= 300) }
end

local function visible_list()
  local v, p, guard = {}, verify.u32('object_head'), 0
  while p ~= 0 and guard < 300 do
    v[#v + 1] = verify.s32(p + 44)
    p = verify.u32(p)
    guard = guard + 1
  end
  return v
end

local function eye()
  local b = verify.resolve('cam_eye')
  return { verify.s32(b), verify.s32(b + 4), verify.s32(b + 8) }
end

local function snap(name)
  local s = { name = name, game_state = s32('game_state'), state_changes = s32('state_changes'), submitted = s32('submitted_objects'),
              prims = s32('prims_submitted'), dropped = s32('prims_dropped'), visible = visible_list(), frame_no = s32('frame_no'), eye = eye(),
              yaw = s32('cam_yaw') }
  out.snaps[#out.snaps + 1] = s
end

local function info()
  local sh, base, cnt = {}, verify.resolve('scene_shapes'), s32('scene_shape_count')
  for i = 0, math.min(math.max(cnt, 0), 16) - 1 do
    local a = base + i * verify.sym_size_shape
    sh[#sh + 1] = { name = verify.read_bytes(a, 16), radius = s32(a + 16) }
  end
  local st = verify.resolve('store')
  local count = s32(st)
  local tex = { count }
  for i = 0, math.min(math.max(count, 0), 255) * 6 - 1 do tex[#tex + 1] = verify.u16(st + 12 + 2 * i) end
  verify.record('info', { load_status = s32('load_status'), tpk_status = s32('tpk_status'), scene_status = s32('scene_status'),
                          scene_shp_status = s32('scene_shp_status'), object_count = s32('object_count'), shape_count = cnt,
                          cull_radius = s32('scene_cull_radius'), proj_h = s32('proj_h'), shapes = sh, list = walk(), store = tex,
                          game_state = s32('game_state'), eye = eye(), yaw = s32('cam_yaw'),
                          pool = verify.resolve('object_pool'), head = verify.u32('object_head') })
end

verify.sym_size_shape = 100   -- sizeof(SceneShape), fixed by a _Static_assert in scene.h

local pending = nil      -- scenario index posed at the end of the previous frame
verify.on_exec('frame_done', function()
  local n = s32('frame_no')
  if n == 3 then info() end
  if n == 5 then snap('title'); verify.screenshot('title') end
  if n == 6 then verify.button_down('START') end
  if n == 26 then verify.button_up('START') end
  if n >= 6 and n <= 34 then
    out.trace[#out.trace + 1] = { n, s32('game_state'), s32('state_changes') }
  end
  if n == 34 then snap('game1'); verify.screenshot('game1') end
  if n == 36 then verify.button_down('START') end
  if n == 48 then verify.button_up('START') end
  if n >= 36 and n <= 56 then
    out.trace[#out.trace + 1] = { n, s32('game_state'), s32('state_changes') }
  end
  if n == 56 then snap('title2'); verify.screenshot('title2') end
  if n == 58 then verify.button_down('START') end
  if n == 60 then verify.button_up('START') end
  if n == 66 then snap('game2') end
  if n == 68 then verify.button_down('UP'); verify.button_down('RIGHT'); verify.button_down('R1'); verify.button_down('R2') end
  if n == 78 then verify.button_up('UP'); verify.button_up('RIGHT'); verify.button_up('R1'); verify.button_up('R2') end
  if n >= 68 and n <= 86 then
    local e = eye()
    out.fly[#out.fly + 1] = { n, e[1], e[2], e[3], s32('cam_yaw') }
  end
  if n >= 88 then
    if pending then
      local c = cams[pending]
      out.scenarios[#out.scenarios + 1] = { k = pending, eye = eye(), yaw = s32('cam_yaw'), game_state = s32('game_state'), submitted = s32('submitted_objects'),
                                            prims = s32('prims_submitted'), dropped = s32('prims_dropped'), visible = visible_list(), frame_no = n }
      verify.screenshot('s' .. pending)
    end
    local nxt = (pending or 0) + 1
    if cams[nxt] then
      local c = cams[nxt]
      local b = verify.resolve('cam_eye')
      verify.write_u32(b, c.x % 4294967296); verify.write_u32(b + 4, c.y % 4294967296); verify.write_u32(b + 8, c.z % 4294967296)
      verify.write_u32('cam_yaw', c.yaw % 4096)
      pending = nxt
    else
      -- end: the primitive buffers' guard bytes
      local base, g = verify.resolve('ot_frames'), {}
      for f = 0, 1 do
        local raw, t = verify.read_bytes(base + f * FRAME_SZ + 64 * 4 + 2048, 16), {}
        for i = 1, 16 do t[i] = raw:byte(i) end
        g[#g + 1] = t
      end
      verify.record('guards', g)
      verify.collect('done')
    end
  end
end)
