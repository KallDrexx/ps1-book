-- Chapter 41 probe. Boots from the disc image; checks.py writes PARAMS (a Lua table) and then dofile()s this file.
--
-- PARAMS.mode == 'unit': direct calls of the reader's functions, made with directcall.lua when `main` is first reached (before any of the program's own
--   code ran).  PARAMS = { images = { { addr, file }, ... }   files copied to RAM (the generated .TRK images)
--                          calls  = { { fn, a0..a3, tag, limit, writes = { { addr | sym, off, words }, ... }, reads = { { name, addr | sym, off, n }, ... } }, ... } }
--   Record per call: v0, returned, instrs, clobbered, out = { name = { words } }.
--
-- PARAMS.mode == 'game': a driven run of the whole program (README 5.10).
--   PARAMS = { patch = { 'symbol+off' = value, ... },       words written at the entry of main (the constants are pinned to the README's values)
--              start_frame = n,                             START (held 3 frames) on the title at this frame_no
--              track2 = true,                               RIGHT (held 3) four frames before START: the title's menu picks track 2
--              bot = true,                                  while the state is RACE a pilot writes the pad (README 5.10); otherwise the pad is empty
--              ghosts = { { pose, pose, ... }, ... },       race number r (1, 2, ...): one pose per RACE frame, written into `ship` after the frame
--                                                           (x, y, z, speed, yaw, pitch, roll, yaw_vel, section): the next row has posed = true
--              results_wait = n,                            frames in RESULTS before CROSS is pressed (the restart); nil = stay
--              race_wait = n,                               after the restart: frames in RACE before START is pressed (abort to the title)
--              results_exit = 'START',                      press this button 10 frames after the RESULTS state begins (leave for the title)
--              tail = n,                                    frames to keep recording at the end }
--   After every frame from the first one in a state other than the title a row is recorded.
if not PARAMS and os.getenv('CH41_PARAMS') then dofile(os.getenv('CH41_PARAMS')) end
local P = PARAMS or {}

local ffi = require('ffi')
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
  local images_done = false
  local function base_of(w) return (w.addr or verify.resolve(w.sym)) + (w.off or 0) end
  for _, spec in ipairs(P.calls or {}) do
    local c = { fn = spec.fn, a0 = spec.a0, a1 = spec.a1, a2 = spec.a2, a3 = spec.a3, limit = spec.limit or 200000, tag = spec.tag }
    c.prepare = function()
      if not images_done then
        images_done = true
        local mem = PCSX.getMemPtr()
        for _, im in ipairs(P.images or {}) do
          local f = assert(io.open(im.file, 'rb'))
          local data = f:read('*a')
          f:close()
          ffi.copy(mem + (im.addr % 0x200000), data, #data)
        end
      end
      local cp0 = PCSX.getRegisters().CP0.r
      cp0[12] = bit.bor(tonumber(cp0[12]) % 4294967296, 0x40000000)     -- COP2 on (harmless: nothing here uses the GTE, but isin is plain C)
      for _, w in ipairs(spec.writes or {}) do
        local b = base_of(w)
        for i, v in ipairs(w.words) do verify.write_u32(b + 4 * (i - 1), v % 4294967296) end
      end
    end
    c.check = function(_, rec)
      rec.out = {}
      for _, r in ipairs(spec.reads or {}) do rec.out[r.name] = words(base_of(r), r.n) end
    end
    calls[#calls + 1] = c
  end
  local routines = { 'handling_drag', 'handling_skid', 'handling_pitch_target', 'handling_auto_pitch', 'race_section_step', 'race_tick',
                     'race_countdown_tick', 'race_format_time', 'race_format_text' }
  local d = DC.new { calls = calls, routines = routines, limit = 200000 }
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
  _G.ch41_keep = d.keep
  verify.on_vsync(function()
    if d.phase == 2 then verify.collect('done') end
  end)
  return
end

-- ------------------------------------------------------------------------------------------------------------------------------------
local out = { rows = {}, info = {} }
for k, v in pairs(out) do verify.record(k, v) end

verify.on_exec('main', function()
  for name, v in pairs(P.patch or {}) do verify.write_u32(name, v % 4294967296) end
  return false
end)

local BUTTONS = { 'UP', 'DOWN', 'LEFT', 'RIGHT', 'CROSS', 'CIRCLE', 'SQUARE', 'TRIANGLE', 'L1', 'L2', 'R1', 'R2', 'START', 'SELECT' }
local held = {}
local function set_pad(spec)                       -- spec: 'CROSS,LEFT' ('' = nothing)
  local want = {}
  for name in string.gmatch(spec or '', '[A-Z0-9]+') do want[name] = true end
  for _, b in ipairs(BUTTONS) do
    if want[b] and not held[b] then verify.button_down(b); held[b] = true end
    if not want[b] and held[b] then verify.button_up(b); held[b] = nil end
  end
end

-- the pilot: it steers toward the center of the section LOOK sections ahead (by the links), holding CROSS, braking in sharp corners.
-- It reads the program's own state (ship, ship_section, track), so it drives the same lap for the same code.
local TWO_PI = 2 * math.pi
local LOOK = 3
local function pilot()
  local sb, tb = verify.resolve('ship'), verify.u32('track+8')
  local sec = s32('ship_section')
  if sec < 0 then return 'CROSS' end
  local s2 = sec
  for _ = 1, LOOK do s2 = verify.u16(tb + 64 * s2 + 0x2C) end
  local px, pz = s32(sb + 0), s32(sb + 8)
  local tx, tz = s32(tb + 64 * s2 + 0), s32(tb + 64 * s2 + 8)
  local desired = math.atan2(tx - px, tz - pz)
  local yaw = s32(sb + 40) / 16777216 * TWO_PI
  local err = desired - yaw
  err = err - TWO_PI * math.floor((err + math.pi) / TWO_PI)
  local yv = s32(sb + 52) / 16777216 * TWO_PI
  local speed = s32(sb + 36) / 4096
  local want = math.max(-0.02, math.min(0.02, err * 0.15))
  local pad = 'CROSS'
  if math.abs(err) > 0.5 and speed > 22 then pad = 'SQUARE' end
  if yv < want - 0.003 then pad = pad .. ',RIGHT' elseif yv > want + 0.003 then pad = pad .. ',LEFT' end
  return pad
end

local tick_pads = {}
verify.on_exec('ship_update', function(r)
  if s32('game_state') == 2 then tick_pads[#tick_pads + 1] = tonumber(r.a1) % 65536 end
end)
local sfx = {}
verify.on_exec('audio_play_sfx', function(r) sfx[#sfx + 1] = s32('game_state') * 100 + (tonumber(r.a0) % 256) end)

local function text_lines()
  local raw = verify.read_bytes(verify.resolve('race_text'), 12 * 32)
  local t = {}
  for i = 0, 11 do
    local line = raw:sub(i * 32 + 1, i * 32 + 32)
    local z = line:find('\0', 1, true)
    t[#t + 1] = z and line:sub(1, z - 1) or line
  end
  return t
end

local function read_row(pad)
  local pads = tick_pads
  tick_pads = {}
  local fx = sfx
  sfx = {}
  return { pad = pad, pads = pads, sfx = fx, n = s32('frame_no'), state = s32('game_state'), changes = s32('state_changes'), section = s32('ship_section'),
           ticks = s32('frame_ticks'), sticks = s32('ship_ticks'), ship = words(verify.resolve('ship'), 14), cs = words(verify.resolve('collide_state'), 12),
           race = words(verify.resolve('race'), 19), best = s32('race_best'), text = text_lines(), hz = nil,
           sel = s32('track_selected'), stats = words(verify.resolve('audio_stats'), 3) }
end

local function apply_pose(p)
  local sb = verify.resolve('ship')
  verify.write_u32(sb + 0, p[1] % 4294967296)
  verify.write_u32(sb + 4, p[2] % 4294967296)
  verify.write_u32(sb + 8, p[3] % 4294967296)
  for o = 12, 32, 4 do verify.write_u32(sb + o, 0) end
  verify.write_u32(sb + 36, (p[4] or 0) % 4294967296)
  verify.write_u32(sb + 40, (p[5] or 0) % 4294967296)
  verify.write_u32(sb + 44, (p[6] or 0) % 4294967296)
  verify.write_u32(sb + 48, (p[7] or 0) % 4294967296)
  verify.write_u32(sb + 52, (p[8] or 0) % 4294967296)
  if p[9] then verify.write_u32('ship_section', p[9] % 4294967296) end
end

local pulse, wait = nil, 0
local race_no, prev_state, ghost_i = 0, 0, 0
local restarted, finished_frames, started, posed_next, exited = false, 0, false, false, false
local pad_now = ''

verify.on_exec('frame_done', function()
  local n = s32('frame_no')
  local state = s32('game_state')
  if n == 3 then
    out.info.load_status = s32('load_status')
    out.info.track_status = s32('track_status')
    out.info.hz = (s32('video_mode') ~= 0) and 50 or 60
  end
  if state ~= 0 then started = true end
  if started then
    local row = read_row(pad_now)
    row.posed = posed_next
    posed_next = false
    out.rows[#out.rows + 1] = row
  end

  local want = ''
  if state == 0 then
    if not started then
      if P.track2 and n == (P.start_frame or 6) - 4 then pulse = { 'RIGHT', 3 } end
      if n == (P.start_frame or 6) then pulse = { 'START', 3 } end
    else
      finished_frames = finished_frames + 1                    -- back on the title after an abort
      if finished_frames >= (P.tail or 10) then verify.collect('done') end
    end
  elseif state == 1 then
    wait = 0
  elseif state == 2 then
    if prev_state ~= 2 then race_no = race_no + 1; ghost_i = 0 end
    local g = P.ghosts and P.ghosts[race_no]
    if g then
      ghost_i = ghost_i + 1
      if g[ghost_i] then apply_pose(g[ghost_i]); posed_next = true end
    end
    if P.bot then want = pilot() end
    if restarted and P.race_wait then
      wait = wait + 1
      if wait >= P.race_wait then pulse = { 'START', 3 }; wait = -1000000 end
    end
  elseif state == 3 then
    wait = wait + 1
    if P.results_exit and wait >= 10 and not exited then
      pulse = { P.results_exit, 3 }
      exited = true
    elseif P.results_wait and not restarted and wait >= P.results_wait then
      pulse = { 'CROSS', 3 }
      restarted = true
      wait = 0
    elseif (not P.results_wait and not P.results_exit) or (restarted and not P.race_wait) then
      finished_frames = finished_frames + 1
      if finished_frames >= (P.tail or 10) then verify.collect('done') end
    end
  end
  prev_state = state
  if pulse then
    want = pulse[1]
    pulse[2] = pulse[2] - 1
    if pulse[2] <= 0 then pulse = nil end
  end
  pad_now = want
  set_pad(want)
end)
