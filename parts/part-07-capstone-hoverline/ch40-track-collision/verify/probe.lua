-- Chapter 40 probe. Boots from the disc image; checks.py writes PARAMS (a Lua table) and then dofile()s this file.
--
-- PARAMS.mode == 'unit': direct calls of the reader's functions, made with directcall.lua when `main` is first reached (before any of the program's own
--   code ran: the track is NOT loaded, so the calls get track images that this probe copies into free RAM).
--   PARAMS = { images = { { addr, file }, ... }       files copied to RAM (the generated .TRK images)
--              calls  = { { fn, a0..a3, tag, limit, writes = { { addr | sym, off, words }, ... }, reads = { { name, addr | sym, off, n }, ... } }, ... } }
--   Record per call: v0, returned, instrs, clobbered, out = { name = { words } }.
--
-- PARAMS.mode == 'game': a driven run of the whole program (README 5.10).
--   PARAMS = { patch = { symbol = value, ... },           words written at the entry of main
--              title = { { frame = n, button = 'RIGHT', hold = 2 }, ... },   pad presses while the title is shown (frame_no is the clock)
--              snaps = { frame_no, ... },                 state snapshots taken on the title at the end of these frames
--              segments = { { pose = { x, y, z, speed, yaw, pitch, roll, yaw_vel, section }, pads = { { 'CROSS,LEFT', frames }, ... } }, ... } }
--   START (hold 2) enters the game on `start_frame`. In the game, segment s starts by writing its pose into `ship` (pos, pos_frac = 0, vel = 0, speed,
--   yaw, pitch, roll, yaw_vel) and, if given, `ship_section`; then the pad runs are played one frame each. After every game frame a row is recorded.
if not PARAMS and os.getenv('CH40_PARAMS') then dofile(os.getenv('CH40_PARAMS')) end
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
      cp0[12] = bit.bor(tonumber(cp0[12]) % 4294967296, 0x40000000)     -- COP2 on: the ship code does not use the GTE, but the SDK's isin is plain C; harmless
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
  local routines = { 'collide_ship', 'collide_edges', 'collide_edge_dist', 'collide_section', 'collide_ground', 'collide_floor_face', 'collide_respawn' }
  local d = DC.new { calls = calls, routines = routines, limit = 200000 }
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
  _G.ch40_keep = d.keep
  verify.on_vsync(function()
    if d.phase == 2 then verify.collect('done') end
  end)
  return
end

-- ------------------------------------------------------------------------------------------------------------------------------------
local out = { rows = {}, info = {}, snaps = {} }
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
    if not want[b] and held[b] and b ~= 'START' then verify.button_up(b); held[b] = nil end
  end
end

local function track_info()
  local img = verify.u32('track_image')
  local t = { sel = s32('track_selected'), status = s32('track_status'), load_status = s32('load_status'), track = words(verify.resolve('track'), 12),
              image = img, music = s32('audio_stats+8'), frame = s32('frame_no') }
  if img ~= 0 then t.name = verify.read_bytes(img + 8, 8) end
  local sec = verify.u32('track+8')
  if sec ~= 0 then t.sec0 = words(sec, 16) end
  return t
end

local seg_i, k, run_i, run_k = 0, 0, 1, 0
local segs = P.segments or {}
local finished, tail = false, 0
local pad_now = ''

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

local function next_pad()                          -- the pad for the next frame of the current segment
  local seg = segs[seg_i]
  while seg.pads[run_i] and run_k >= seg.pads[run_i][2] do run_i = run_i + 1; run_k = 0 end
  if not seg.pads[run_i] then return nil end
  run_k = run_k + 1
  return seg.pads[run_i][1]
end

local function start_segment()
  seg_i = seg_i + 1
  k, run_i, run_k = 0, 1, 0
  if seg_i > #segs then return false end
  apply_pose(segs[seg_i].pose)
  return true
end

-- the pad ship_update was REALLY given on every tick (the emulated pad reaches the program a frame late, so the scripted mask is only the intention)
local tick_pads = {}
verify.on_exec('ship_update', function(r)
  if s32('game_state') == 1 then tick_pads[#tick_pads + 1] = tonumber(r.a1) % 65536 end
end)

local function read_row(pad)
  local text = verify.read_bytes(verify.resolve('collide_text'), 32)
  local z = text:find('\0', 1, true)
  if z then text = text:sub(1, z - 1) end
  local pads = tick_pads
  tick_pads = {}
  return { seg = seg_i, k = k, pad = pad, pads = pads, n = s32('frame_no'), section = s32('ship_section'), ticks = s32('frame_ticks'), sticks = s32('ship_ticks'),
           ship = words(verify.resolve('ship'), 14), cs = words(verify.resolve('collide_state'), 12), thud = s32('audio_stats+16'), boost = s32('audio_stats+12'),
           text = text }
end

verify.on_exec('frame_done', function()
  local n = s32('frame_no')
  if n == 3 then
    out.info.load_status = s32('load_status')
    out.info.track_status = s32('track_status')
    out.info.start = track_info()
  end
  if s32('game_state') ~= 1 then
    for _, ev in ipairs(P.title or {}) do
      if n == ev.frame then verify.button_down(ev.button) end
      if n == ev.frame + (ev.hold or 2) then verify.button_up(ev.button) end
    end
    for _, sn in ipairs(P.snaps or {}) do
      if n == sn then out.snaps[#out.snaps + 1] = track_info() end
    end
    if P.start_frame and n == P.start_frame then verify.button_down('START'); held.START = true end
    if P.start_frame and n == P.start_frame + 2 then verify.button_up('START'); held.START = nil end
    return
  end
  if finished then
    tail = tail + 1
    if tail == 3 then
      out.info.end_track = track_info()
      verify.collect('done')
    end
    return
  end
  if seg_i == 0 then                                 -- the first game frame: no tick has run yet
    if held.START then verify.button_up('START'); held.START = nil end   -- START was still down when the game state began
    out.info.entry = { ship = words(verify.resolve('ship'), 14), section = s32('ship_section'), cs = words(verify.resolve('collide_state'), 12),
                       track = track_info(), ticks = s32('ship_ticks'), frame = n }
    if not start_segment() then finished = true; return end
    pad_now = next_pad() or ''
    set_pad(pad_now)
    return
  end
  out.rows[#out.rows + 1] = read_row(pad_now)
  k = k + 1
  local nxt = next_pad()
  if not nxt then
    if not start_segment() then
      finished = true
      set_pad('')
      return
    end
    nxt = next_pad() or ''
  end
  pad_now = nxt
  set_pad(pad_now)
end)
