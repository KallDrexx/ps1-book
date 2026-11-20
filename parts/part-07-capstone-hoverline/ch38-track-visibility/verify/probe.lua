-- Chapter 38 probe. Boots from the disc image; checks.py writes PARAMS (a Lua table) and then dofile()s this file.
--
-- PARAMS = { poses = { { x, y, z, yaw (12.12), tag }, ... }, patch = { vis_ahead = n, ... }, shots = { { name, pose_index }, ... },
--            frame_sz = n, vertex_count = n, end_frame = n }
--
-- How it drives a lap (README 5.9): the ship has no collision yet and flies straight, so the lap is NOT driven by the pad. At the end of every frame
-- (the program's `frame_done`) the probe writes the NEXT pose into `ship` (pos, pos_frac = 0, yaw, pitch = 0, roll = 0, speed = 0, vel = 0, yaw_vel = 0).
-- The pad is idle, so ship_update leaves that state alone (speed 0: pos += 0); the game then runs chase_camera_update, the visibility update and the draw for
-- that pose. At the NEXT frame_done the probe records the row for it: ship_section, the counters, the vertex states, the packets of the frame's ordering table.
-- Patches (vis_ahead, vis_behind, vis_mode, vis_lost, subdiv_enabled, video_mode) are written at the entry of `main`.
if not PARAMS and os.getenv('CH38_PARAMS') then dofile(os.getenv('CH38_PARAMS')) end
local P = PARAMS or {}

local function s32(a) return verify.s32(a) end
local function words(addr, n)
  local t = {}
  for i = 0, n - 1 do t[#t + 1] = verify.s32(addr + 4 * i) end
  return t
end

PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
  local cp0 = PCSX.getRegisters().CP0.r
  local code = math.floor((tonumber(cp0[13]) or 0) / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = (tonumber(cp0[14]) or 0) % 4294967296, badvaddr = (tonumber(cp0[8]) or 0) % 4294967296 })
  verify.finish('exception')
  return false
end)

local FRAME_SZ = P.frame_sz or (64 * 4 + 32768 + 16)
local OT_LEN = 64
local out = { rows = {}, vbl_cycles = {}, shots = {}, info = {}, upd = {} }
for k, v in pairs(out) do verify.record(k, v) end

verify.on_exec('main', function()
  for name, v in pairs(P.patch or {}) do verify.write_u32(name, v % 4294967296) end
  return false
end)

-- vertical blanks and the cycles of the last one
local vbl, last_cyc, work, fd_cyc = 0, nil, nil, nil
verify.on_vsync(function()
  local c = verify.cycles()
  vbl = vbl + 1
  if last_cyc and #out.vbl_cycles < 4000 then out.vbl_cycles[#out.vbl_cycles + 1] = c - last_cyc end
  last_cyc = c
end)

-- the work of a frame: from the previous frame_done (a few cycles after the vertical blank the last VSync(0) waited for) to the call of VSync(0) in
-- display_swap: input, update, visibility, draw and the DMA wait of DrawSync. Over 566,120 (NTSC) the frame misses its blank.
verify.on_exec('VSync', function(r)
  if tonumber(r.a0) % 4294967296 == 0 and fd_cyc and not work then work = verify.cycles() - fd_cyc end
end)

-- every track_nearest_update call: its cycles and the brute-force runs it caused
local keep = {}
local upd_open = nil
verify.on_exec('track_nearest_update', function(r)
  if s32('game_state') ~= 1 then return end
  local ra = tonumber(r.ra) % 4294967296
  local c0, b0 = verify.cycles(), s32('vis_brute_runs')
  keep[#keep + 1] = PCSX.addBreakpoint(ra, 'Exec', 4, 'update return', function()
    if #out.upd < 4000 then out.upd[#out.upd + 1] = { cyc = verify.cycles() - c0, brute = s32('vis_brute_runs') - b0, frame = s32('frame_no') } end
    return false
  end)
end)

-- the packets of the ordering table DrawOTag was given in the last frame: command byte -> count
local function walk(frame_idx)
  local base = verify.resolve('ot_frames') + frame_idx * FRAME_SZ
  local lo, hi = base, base + OT_LEN * 4
  local node, hist, n = base + (OT_LEN - 1) * 4, {}, 0
  local mem = PCSX.getMemPtr()
  while n < 4000 do
    local w = verify.u32(node)
    local nxt = w % 16777216
    if nxt == 16777215 then break end
    node = 0x80000000 + nxt
    if node < lo or node >= hi then
      local cmd = mem[(node + 7) % 0x200000]
      hist[tostring(cmd)] = (hist[tostring(cmd)] or 0) + 1
    end
    n = n + 1
  end
  return hist
end

local function vstates()
  local cnt = P.vertex_count or 1024
  local base = verify.resolve('trk_vstate')
  local raw = verify.read_bytes(base, cnt)
  local t = {}
  for i = 1, cnt do t[i] = string.char(48 + raw:byte(i)) end
  return table.concat(t)
end

local idx = 0                      -- poses applied so far
local finished = false
local shots_done = {}

verify.on_exec('frame_done', function()
  local n = s32('frame_no')
  if n == 3 then
    out.info.load_status = s32('load_status')
    out.info.track_status = s32('track_status')
    out.info.tex_status = s32('tex_status')
    out.info.vis_list_done = s32('vis_list_done')
  end
  if n == 6 then verify.button_down('START') end
  if n == 8 then verify.button_up('START') end
  if s32('game_state') ~= 1 or finished then return end

  if idx == 0 then
    out.info.start_row = { section = s32('ship_section'), ship = words(verify.resolve('ship'), 14), frame = n }
  end
  if idx > 0 then
    local k = idx
    local f = (n - 1) % 2
    local row = { n = n, pose = k, section = s32('ship_section'), prims = s32('prims_this_frame'), first = s32('vis_first'), count = s32('vis_count'),
                  brute = s32('vis_brute_runs'), ticks = s32('frame_ticks'), vbl = vbl, work = work or -1, cyc = verify.cycles(),
                  stats = words(verify.resolve('track_stats'), 8), ahead = s32('vis_ahead'), behind = s32('vis_behind'),
                  ship = words(verify.resolve('ship'), 3), hist = walk(f), vs = vstates(), submitted = s32('prims_submitted') }
    local t = {}
    local base = verify.resolve('vis_text')
    local raw = verify.read_bytes(base, 32)
    for i = 1, 32 do local b = raw:byte(i); if b == 0 then break end; t[#t + 1] = string.char(b) end
    row.text = table.concat(t)
    out.rows[#out.rows + 1] = row
    for _, sh in ipairs(P.shots or {}) do
      if not shots_done[sh[1]] and k >= sh[2] then
        shots_done[sh[1]] = true
        verify.screenshot(sh[1])
        out.shots[#out.shots + 1] = { name = sh[1], pose = k, row = #out.rows }
      end
    end
  end
  work = nil
  fd_cyc = verify.cycles()
  local poses = P.poses or {}
  if idx >= #poses or n >= (P.end_frame or 2000) then
    finished = true
    local g = {}
    local base = verify.resolve('ot_frames')
    for f = 0, 1 do
      local raw, t = verify.read_bytes(base + f * FRAME_SZ + FRAME_SZ - 16, 16), {}
      for i = 1, 16 do t[i] = raw:byte(i) end
      g[#g + 1] = t
    end
    verify.record('guards', g)
    verify.collect('done')
    return
  end
  idx = idx + 1
  local p = poses[idx]
  local sb = verify.resolve('ship')
  verify.write_u32(sb + 0, p[1] % 4294967296)
  verify.write_u32(sb + 4, p[2] % 4294967296)
  verify.write_u32(sb + 8, p[3] % 4294967296)
  for o = 12, 36, 4 do verify.write_u32(sb + o, 0) end      -- pos_frac, vel, speed
  verify.write_u32(sb + 40, (p[4] * 4096) % 4294967296)     -- yaw
  verify.write_u32(sb + 44, 0)                              -- pitch
  verify.write_u32(sb + 48, 0)                              -- roll
  verify.write_u32(sb + 52, 0)                              -- yaw_vel
end)
_G.ch38_keep = keep
