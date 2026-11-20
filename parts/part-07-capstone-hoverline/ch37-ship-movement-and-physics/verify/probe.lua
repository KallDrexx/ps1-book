-- Chapter 37 probe. Observes; boots from the disc image. checks.py writes PARAMS (a Lua table) and then dofile()s this file.
-- PARAMS.mode == 'game' (a driven run) or 'unit' (direct calls only):
--
-- 'game':  PARAMS = { pal = 0|1, subdiv = 0|1, cfg = { [word index] = value }, ticks = { { button, first_tick, last_tick }, ... }, end_tick = n,
--                      shots = { { name, tick }, ... }, r1_tick = n or nil, frame_sz = n }
--   At the entry of `main` (after the SDK's startup, before any of the program's code) video_mode, subdiv_enabled and the constants of
--   ship_cfg are written. The program is driven by frame_no (START held on frames 6..8: title -> game); inside the game the script is
--   driven by ship_ticks: a button is held while first_tick <= ship_ticks < last_tick, checked at the end of every frame.
--   `calls`: every ship_update call of the game (hooked at its entry and at its return): { pad, dt, before = {14 words}, after = {14 words} }.
--   `rows`:  one per game frame (at frame_done): { n, cyc, vbl (vertical blanks so far), ticks (frame_ticks), sticks (ship_ticks), subdiv,
--            ship = {14}, eye = {3}, tgt = {3} }.
--   `vbl_cycles`: the CPU cycles between consecutive vertical blanks (the emulated frame period).
--   `info`: statuses, video_mode, dt_scale, the first game frame's row. `shots`: { name, tick, row } for each screenshot taken.
-- 'unit':  PARAMS = { calls = { { fn, a0, a1, a2, writes = { { addr | sym, words } }, reads = { { name, addr | sym, n } } }, ... } }
--   Every call is made with directcall.lua when `main` is first reached; records: v0, returned, instrs, clobbered, out = { name = { words } }.
if not PARAMS and os.getenv('CH37_PARAMS') then dofile(os.getenv('CH37_PARAMS')) end
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

-- ------------------------------------------------------------------------------------------------------------------------------------
if P.mode == 'unit' then
  local DC = dofile(verify.libdir .. '/directcall.lua')
  local calls = {}
  for _, spec in ipairs(P.calls or {}) do
    local c = { fn = spec.fn, a0 = spec.a0, a1 = spec.a1, a2 = spec.a2, a3 = spec.a3, limit = spec.limit or 60000, tag = spec.tag }
    c.prepare = function()
      -- the GTE is switched off until InitGeom (which `main` calls later): switch COP2 on in the status register
      local cp0 = PCSX.getRegisters().CP0.r
      cp0[12] = bit.bor(tonumber(cp0[12]) % 4294967296, 0x40000000)
      for _, w in ipairs(spec.writes or {}) do
        local base = w.addr or verify.resolve(w.sym)
        for i, v in ipairs(w.words) do verify.write_u32(base + 4 * (i - 1), v % 4294967296) end
      end
    end
    c.check = function(_, rec)
      rec.out = {}
      for _, r in ipairs(spec.reads or {}) do
        rec.out[r.name] = words(r.addr or verify.resolve(r.sym), r.n)
      end
    end
    calls[#calls + 1] = c
  end
  local d = DC.new{ calls = calls, routines = { 'ship_update', 'ship_forward', 'ship_matrix', 'chase_camera_update', 'heading_angle', 'pitch_angle' },
                    limit = 60000 }
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
  _G.ch37_keep = d.keep
  verify.on_vsync(function()
    if d.phase == 2 then verify.collect('done') end
  end)
  return
end

-- ------------------------------------------------------------------------------------------------------------------------------------
local FRAME_SZ = P.frame_sz or (64 * 4 + 32768 + 16)
local out = { rows = {}, calls = {}, vbl_cycles = {}, shots = {}, info = {} }
for k, v in pairs(out) do verify.record(k, v) end

verify.on_exec('main', function()
  verify.write_u32('video_mode', P.pal or 0)
  verify.write_u32('subdiv_enabled', P.subdiv or 0)
  local base = verify.resolve('ship_cfg')
  for i, v in pairs(P.cfg or {}) do verify.write_u32(base + 4 * i, v % 4294967296) end
  return false
end)

local vbl, last_cyc = 0, nil
verify.on_vsync(function()
  local c = verify.cycles()
  vbl = vbl + 1
  if last_cyc and #out.vbl_cycles < 4000 then out.vbl_cycles[#out.vbl_cycles + 1] = c - last_cyc end
  last_cyc = c
end)

-- every ship_update call: the state and the arguments at the entry, the state at the return
local recording = false
local keep = {}
verify.on_exec('ship_update', function(r)
  if s32('game_state') ~= 1 then return end
  local ra = tonumber(r.ra) % 4294967296
  local a0 = tonumber(r.a0) % 4294967296
  local call = { pad = tonumber(r.a1) % 65536, dt = tonumber(r.a2) % 4294967296, before = words(a0, 14), ptr = a0 }
  if call.dt >= 2147483648 then call.dt = call.dt - 4294967296 end
  out.calls[#out.calls + 1] = call
  keep[#keep + 1] = PCSX.addBreakpoint(ra, 'Exec', 4, 'ship_update return', function()
    call.after = words(a0, 14)
    return false
  end)
end)

local function down(b) verify.button_down(b) end
local function up(b) verify.button_up(b) end
local held = {}
local shots_done = {}
local r1_state = 0
local finished = false

verify.on_exec('frame_done', function()
  local n = s32('frame_no')
  if n == 3 then
    out.info.load_status = s32('load_status')
    out.info.track_status = s32('track_status')
    out.info.video_mode = s32('video_mode')
    out.info.dt_scale = s32('dt_scale')
  end
  if n == 6 then down('START') end
  if n == 8 then up('START') end
  if s32('game_state') ~= 1 or finished then return end

  local st = s32('ship_ticks')
  local row = { n = n, cyc = verify.cycles(), vbl = vbl, ticks = s32('frame_ticks'), sticks = st, subdiv = s32('subdiv_enabled'),
                ship = words(verify.resolve('ship'), 14), eye = words(verify.resolve('cam_eye'), 3), tgt = words(verify.resolve('cam_target'), 3) }
  out.rows[#out.rows + 1] = row
  for _, sh in ipairs(P.shots or {}) do
    if not shots_done[sh[1]] and st >= sh[2] then
      shots_done[sh[1]] = true
      verify.screenshot(sh[1])
      out.shots[#out.shots + 1] = { name = sh[1], tick = st, row = #out.rows }
    end
  end
  -- the script: hold each button while first <= ship_ticks < last
  local want = {}
  for _, s in ipairs(P.ticks or {}) do
    if st >= s[2] and st < s[3] then want[s[1]] = true end
  end
  for _, s in ipairs(P.ticks or {}) do
    local b = s[1]
    if want[b] and not held[b] then down(b); held[b] = true end
    if not want[b] and held[b] then up(b); held[b] = false end
  end
  if P.r1_tick then
    if r1_state == 0 and st >= P.r1_tick then down('R1'); r1_state = 1; out.info.r1_row = #out.rows
    elseif r1_state == 1 and #out.rows >= (out.info.r1_row or 0) + 6 then up('R1'); r1_state = 2 end
  end
  if st >= (P.end_tick or 300) or n >= (P.end_frame or 520) then
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
  end
end)
_G.ch37_keep = keep
