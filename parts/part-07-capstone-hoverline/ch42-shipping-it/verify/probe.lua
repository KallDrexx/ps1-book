-- Chapter 42 probe: boots the RELEASE disc (release/hoverline.cue) and plays the start of a race. checks.py writes PARAMS and dofile()s this file.
--   PARAMS.pal = true    make the console a PAL one: a PAL BIOS leaves the GPU in its PAL display mode (GPUSTAT bit 20 set) when it starts the game, and OpenBIOS,
--                        which this emulator runs, does not, so a three-instruction stub does what the BIOS would have done (GP1 command 0x08000008)
--                        before `main`'s first instruction. The program has to find out for itself
--   PARAMS.race_frames   how many frames of RACE to record before stopping (CROSS held all the time)
-- Recorded: rows = one table per frame_done (after the first game frame): n, state, ticks, cycles, wire, dbg, sub, speed, text (race_text[0]),
--           info = load_status, video_mode, dt_scale; shots 'count' (a countdown frame) and 'race'.
if not PARAMS and os.getenv('CH42_PARAMS') then dofile(os.getenv('CH42_PARAMS')) end
local P = PARAMS or {}

if P.pal then
  local STUB = 0x80090000
  verify.on_exec('main', function()
    local main = verify.resolve('main')
    verify.write_u32(STUB, 0x3C081F80)                -- lui t0, 0x1f80
    verify.write_u32(STUB + 4, 0x3C090800)            -- lui t1, 0x0800
    verify.write_u32(STUB + 8, 0x35290008)            -- ori t1, t1, 8         GP1(08h): PAL, 256 x 240
    verify.write_u32(STUB + 12, 0xAD091814)           -- sw  t1, 0x1814(t0)
    verify.write_u32(STUB + 16, 0x08000000 + math.floor((main % 0x10000000) / 4))   -- j main
    verify.write_u32(STUB + 20, 0)
    PCSX.getRegisters().pc = STUB
    return false
  end)
end

local function s32(a) return verify.s32(a) end

PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
  local cp0 = PCSX.getRegisters().CP0.r
  local code = math.floor((tonumber(cp0[13]) or 0) / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = (tonumber(cp0[14]) or 0) % 4294967296, badvaddr = (tonumber(cp0[8]) or 0) % 4294967296 })
  verify.finish('exception')
  return false
end)

local out = { rows = {}, info = {} }
for k, v in pairs(out) do verify.record(k, v) end

local BUTTONS = { 'UP', 'DOWN', 'LEFT', 'RIGHT', 'CROSS', 'CIRCLE', 'SQUARE', 'TRIANGLE', 'L1', 'L2', 'R1', 'R2', 'START', 'SELECT' }
local held = {}
local function set_pad(spec)
  local want = {}
  for name in string.gmatch(spec or '', '[A-Z0-9]+') do want[name] = true end
  for _, b in ipairs(BUTTONS) do
    if want[b] and not held[b] then verify.button_down(b); held[b] = true end
    if not want[b] and held[b] then verify.button_up(b); held[b] = nil end
  end
end

local function first_line(sym, size)
  local raw = verify.read_bytes(verify.resolve(sym), size)
  local z = raw:find('\0', 1, true)
  return z and raw:sub(1, z - 1) or raw
end

local in_state = { 0, 0, 0, 0 }          -- frames spent in each state so far
local race_rows = 0
local started = false

verify.on_exec('frame_done', function()
  local n = s32('frame_no')
  local state = s32('game_state')
  if n == 3 then
    out.info.load_status = s32('load_status')
    out.info.video_mode = s32('video_mode')
    out.info.dt_scale = s32('dt_scale')
  end
  if state ~= 0 then started = true end
  if started then
    in_state[state + 1] = in_state[state + 1] + 1
    out.rows[#out.rows + 1] = { n = n, state = state, ticks = s32('frame_ticks'), cycles = verify.cycles(), wire = s32('wire_mode'),
                                dbg = s32('subdiv_debug'), sub = s32('subdiv_enabled'), speed = s32(verify.resolve('ship') + 36),
                                text = first_line('race_text', 32) }
  end

  local pad = ''
  local k = in_state[state + 1]
  if state == 0 then
    if not started and n >= 6 and n < 9 then pad = 'START' end
  elseif state == 1 then
    -- debug keys during the countdown
    if k >= 8 and k < 11 then pad = 'SELECT' elseif k >= 16 and k < 19 then pad = 'TRIANGLE' elseif k >= 24 and k < 27 then pad = 'R1' end
    if k == 40 then verify.screenshot('count') end
  elseif state == 2 then
    race_rows = race_rows + 1
    pad = 'CROSS'
    if race_rows >= 10 and race_rows < 13 then pad = 'CROSS,SELECT' elseif race_rows >= 20 and race_rows < 23 then pad = 'CROSS,TRIANGLE'
    elseif race_rows >= 30 and race_rows < 33 then pad = 'CROSS,R1' end
    if race_rows == (P.race_frames or 90) - 5 then verify.screenshot('race') end
    if race_rows >= (P.race_frames or 90) then verify.collect('done') end
  end
  set_pad(pad)
end)
