-- Chapter 39 probe. Boots from the disc image; checks.py writes PARAMS (a Lua table) and then dofile()s this file.
--
-- PARAMS = { calls = { {fn, a0, ...}, ... }       direct calls of audio_pitch_for_speed / audio_voice_alloc (made at the entry of main)
--            poses = { {x, y, z, speed, yaw12}, ...}  the scripted run: one pose per frame (see below)
--            patch = { name = value, ... }        words written at the entry of main (audio_cfg+4 ...)
--            spd = "/path/dump.spd", title_return = true, shots = {...} }
--
-- How the run is driven (README 5.9): the pad is idle except for START. At the end of every frame (the program's `frame_done`) the probe writes the
-- NEXT pose into `ship` (pos, pos_frac = 0, yaw, pitch = 0, roll = 0, yaw_vel = 0, vel = 0, speed = the pose's speed); the next frame then runs ship_update (speed 0:
-- the position stays; speed > 0: the ship moves a little, which the scripted speed sweeps do not care about), the section update, the audio events and the engine update.
--
-- What is recorded (the SPU is not readable from Lua: README 5.9 of the chapter):
--   log   one string per store into the SPU registers (0x1F801C00..0x1F801DFF) or the CD controller (0x1F801800..03): "pose offset width value";
--         `pose` is the index of the pose the frame belongs to (0 before the first pose). checks.py replays them to know every register and every key-on.
--   rows  per pose: ship_section, ship.speed, game_state and the 12 words of audio_stats, as the frame left them.
--   calls the direct-call records.
if not PARAMS and os.getenv('CH39_PARAMS') then dofile(os.getenv('CH39_PARAMS')) end
local P = PARAMS or {}

local function s32(a) return verify.s32(a) end
local function words(addr, n)
  local t = {}
  for i = 0, n - 1 do t[#t + 1] = verify.s32(addr + 4 * i) end
  return t
end

-- the SPU dump needs the logger running from the start (README 5.9): it is what makes PCSX-Redux keep a register stream, and the dump carries the RAM image
if P.spd then PCSX.SPU.Logger.enable() end

local out = { log = {}, rows = {}, info = {}, calls = {}, seeds = {} }
for k, v in pairs(out) do verify.record(k, v) end

-- ---------------------------------------------------------------- direct calls (phase 1, before the program runs)
local DC = dofile(verify.libdir .. '/directcall.lua')
local saved = {}
local function poke(sym, off, v) verify.write_u32(sym .. '+' .. off, v % 4294967296) end
local calls = {}
for i, c in ipairs(P.calls or {}) do
  local call = { fn = c.fn, a0 = c.a0, tag = c.tag, rate = c.rate, idle = c.idle, span = c.span }
  if c.fn == 'audio_pitch_for_speed' then
    call.prepare = function()
      saved = { rate = verify.u32('audio_samples+8'), addr = verify.u32('audio_samples+0'), idle = verify.u32('audio_cfg+0'), span = verify.u32('audio_cfg+4') }
      poke('audio_samples', 0, c.addr or 0x1010)
      poke('audio_samples', 8, c.rate)
      poke('audio_cfg', 0, c.idle)
      poke('audio_cfg', 4, c.span)
    end
    call.check = function(_, rec)
      poke('audio_samples', 0, saved.addr); poke('audio_samples', 8, saved.rate); poke('audio_cfg', 0, saved.idle); poke('audio_cfg', 4, saved.span)
    end
  end
  calls[#calls + 1] = call
end
if #calls > 0 then
  local d = DC.new { calls = calls, routines = { 'audio_pitch_for_speed', 'audio_voice_alloc' }, limit = 4000 }
  d.keep = d.keep
  _G.ch39_dc = d
  verify.record('calls', d.records)
  verify.record('seed', DC.seed)
end

verify.on_exec('main', function()
  for name, v in pairs(P.patch or {}) do verify.write_u32(name, v % 4294967296) end
  return false
end)

-- ---------------------------------------------------------------- hardware register stores
local cur = 0
local nlog = 0
local cd_bank = 0
out.info.play_vb = {}                                         -- the emulator frame (vblank count) of every CdlPlay: the restart must wait for the end of the track
local function logit(off, w, v)
  if off == 0x1800 then cd_bank = v % 4
  elseif off == 0x1801 and cd_bank == 0 and v == 3 then out.info.play_vb[#out.info.play_vb + 1] = verify.frame end
  if nlog < 60000 then
    nlog = nlog + 1
    out.log[nlog] = string.format('%d %x %d %x', cur, off, w, v)
  end
end
verify.on_hwwrite(0x1F801C00, 0x200, logit)
verify.on_hwwrite(0x1F801800, 4, logit)

-- ---------------------------------------------------------------- the script
local idx, finished, tail = 0, false, 0
local frames_in_game = 0

local function read_row()
  return { pose = idx, n = s32('frame_no'), section = s32('ship_section'), speed = s32('ship+36'), state = s32('game_state'),
           stats = words(verify.resolve('audio_stats'), 12), pos = words(verify.resolve('ship'), 3) }
end

verify.on_exec('frame_done', function()
  local n = s32('frame_no')
  if n == 3 then
    out.info.load_status = s32('load_status')
    out.info.audio_status = s32('audio_status')
    out.info.samples = words(verify.resolve('audio_samples'), 20)
    out.info.stats_at_title = words(verify.resolve('audio_stats'), 12)
    out.info.n_log_at_title = nlog
  end
  if P.start_frame and n == P.start_frame then verify.button_down('START') end
  if P.start_frame and n == P.start_frame + 2 then verify.button_up('START') end
  if finished then
    tail = tail + 1
    if tail == 4 then
      out.rows[#out.rows + 1] = read_row()
      if P.spd then
        local ok, err = PCSX.SPU.Logger.exportSPD(P.spd, 0, true)
        out.info.spd_ok = tostring(ok) .. ' ' .. tostring(err)
      end
      verify.collect('done')
    end
    return
  end
  if s32('game_state') ~= 1 then return end
  frames_in_game = frames_in_game + 1
  if idx > 0 then
    out.rows[#out.rows + 1] = read_row()
    for _, sh in ipairs(P.shots or {}) do
      if idx == sh[2] then verify.screenshot(sh[1]) end
    end
  else
    out.info.entry = read_row()
  end
  local poses = P.poses or {}
  if idx >= #poses then
    finished = true
    if P.title_return then
      verify.button_down('START')
      verify.at_frame(verify.frame + 2, function() verify.button_up('START') end)
    end
    cur = idx + 1
    return
  end
  idx = idx + 1
  cur = idx
  local p = poses[idx]
  local sb = verify.resolve('ship')
  verify.write_u32(sb + 0, p[1] % 4294967296)
  verify.write_u32(sb + 4, p[2] % 4294967296)
  verify.write_u32(sb + 8, p[3] % 4294967296)
  for o = 12, 32, 4 do verify.write_u32(sb + o, 0) end      -- pos_frac, vel
  verify.write_u32(sb + 36, p[4] % 4294967296)              -- speed
  verify.write_u32(sb + 40, ((p[5] or 0) * 4096) % 4294967296)   -- yaw
  verify.write_u32(sb + 44, 0)
  verify.write_u32(sb + 48, 0)
  verify.write_u32(sb + 52, 0)
end)
