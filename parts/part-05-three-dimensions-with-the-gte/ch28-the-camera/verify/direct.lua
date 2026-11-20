-- Chapter 28 direct-call probe: calls the reader's camera_look_at(eye, target, up) from inside frame_done(), once per
-- frame, for a list of cases built here (specials + a seeded pseudo-random set). For each call it records
--   eye, target, up (as passed), view_mtx (9 s16 + 3 s32) afterwards, the arguments re-read afterwards (they must be
--   unchanged), whether the callee-saved registers s0-s7/fp/sp survived, and whether the routine returned.
-- The arguments live in a scratch buffer, NOT in cam_eye/cam_target/cam_up, so a routine that reads those globals
-- instead of its parameters gets the wrong answer. Everything is recorded as the `calls` list.
local ARGS, TRAMP = 0x801E8000, 0x80090000
local R = PCSX.getRegisters()
local GPR = R.GPR.r
local function get(i) return tonumber(GPR[i]) % 4294967296 end
local function set(i, v) GPR[i] = v % 4294967296 end

local seed = 20281120
local function rnd()                     -- 31-bit LCG, uniform in [0, 1)
  seed = (seed * 1103515245 + 12345) % 2147483648
  return seed / 2147483648
end
local function rr(lo, hi) return math.floor(lo + rnd() * (hi - lo + 1)) end

local UP = { 0, -4096, 0 }
local cases = {
  { { 0, 0, -14336 }, { 0, -4000, 1800 }, UP },              -- the shipped start
  { { 0, 0, 0 }, { 0, 0, 5000 }, UP },                       -- looking along +z: the identity
  { { 0, 0, 0 }, { 5000, 0, 0 }, UP },                       -- looking along +x
  { { 0, 0, 0 }, { -5000, 0, 0 }, UP },                      -- looking along -x
  { { 0, 0, 5000 }, { 0, 0, -5000 }, UP },                   -- looking back along -z
  { { 3000, -2000, -8000 }, { 0, 0, 0 }, UP },
  { { 3000, -2000, -8000 }, { 0, 0, 0 }, { 2000, -3500, 1000 } },     -- tilted up: the camera rolls
  { { 3000, -2000, -8000 }, { 0, 0, 0 }, { 0, -3, 0 } },              -- |up| must not matter: tiny ...
  { { 3000, -2000, -8000 }, { 0, 0, 0 }, { 0, -32000, 0 } },          -- ... and huge
  { { 3000, -2000, -8000 }, { 0, 0, 0 }, { 4096, 0, 0 } },            -- up = +x: rolled a quarter turn
  { { 3000, -2000, -8000 }, { 0, 0, 0 }, { 0, 4096, 0 } },            -- up = +y: upside down
  { { -16000, -9000, -16000 }, { 16000, 3000, 16000 }, UP },          -- differences of 32000: overflow if unscaled
  { { 100, 200, 300 }, { 103, 200, 300 }, UP },                       -- a 3-unit look direction
  { { 0, 0, 0 }, { 500, -5000, 0 }, UP },                             -- sin(angle to up) = 0.0995: NOT degenerate
  { { 0, 0, 0 }, { 0, -5000, 0 }, UP },                               -- degenerate: forward = up
  { { 0, 0, 0 }, { 0, 5000, 0 }, UP },                                -- degenerate: forward = down
  { { 0, 0, 0 }, { 78, -5000, 0 }, UP },                              -- degenerate: sin = 1/64
  { { 0, 0, 0 }, { 0, 0, 5000 }, { 0, 0, 4096 } },                    -- degenerate, and so is the +z fallback
  { { 700, 700, 700 }, { 700, 700, 700 }, UP },                       -- eye == target
  { { 0, 0, 0 }, { 400, 300, 5000 }, { 0, 0, 0 } },                   -- no up at all
}
for _ = 1, 16 do
  local e = { rr(-16000, 16000), rr(-16000, 16000), rr(-16000, 16000) }
  local t = { rr(-16000, 16000), rr(-16000, 16000), rr(-16000, 16000) }
  local up = UP
  if rnd() < 0.5 then up = { rr(-4096, 4096), -rr(1000, 32000), rr(-4096, 4096) } end
  local d = { t[1] - e[1], t[2] - e[2], t[3] - e[3] }
  local dl = math.sqrt(d[1] * d[1] + d[2] * d[2] + d[3] * d[3])
  local ul = math.sqrt(up[1] * up[1] + up[2] * up[2] + up[3] * up[3])
  local cx, cy, cz = d[2] * up[3] - d[3] * up[2], d[3] * up[1] - d[1] * up[3], d[1] * up[2] - d[2] * up[1]
  local s = math.sqrt(cx * cx + cy * cy + cz * cz) / (dl * ul)
  if dl > 1000 and s > 0.25 then cases[#cases + 1] = { e, t, up } end
end

local calls = {}
verify.record('calls', calls)
if not (verify.sym.camera_look_at and verify.sym.frame_done) then return end

local fn = verify.resolve('camera_look_at')
local fd = verify.resolve('frame_done')
local idx, saved, saved_pc, sent, cur = 0, nil, 0, nil, nil
local resumed = false

local function s16(a) local v = verify.u16(a); return v >= 32768 and v - 65536 or v end
local function words(a) return { verify.s32(a), verify.s32(a + 4), verify.s32(a + 8) } end

verify.write_u32(TRAMP, 0)
keep_tramp = PCSX.addBreakpoint(TRAMP, 'Exec', 4, 'ch28 return', function()
  if not saved then return end
  local m = {}
  for i = 0, 8 do m[#m + 1] = s16(verify.resolve('view_mtx') + 2 * i) end
  for i = 0, 2 do m[#m + 1] = verify.s32(verify.resolve('view_mtx') + 20 + 4 * i) end
  local kept = true
  for i, r in ipairs({ 16, 17, 18, 19, 20, 21, 22, 23, 30 }) do
    if get(r) ~= sent[i] then kept = false end
  end
  if get(29) ~= sent[10] then kept = false end
  cur.view, cur.returned, cur.kept = m, true, kept
  cur.eye2, cur.target2, cur.up2 = words(ARGS), words(ARGS + 12), words(ARGS + 24)
  calls[#calls + 1] = cur
  for i = 1, 31 do set(i, saved[i]) end
  R.pc = saved_pc
  saved = nil
  resumed = true
end)

-- A CPU exception inside a call (e.g. the arithmetic-overflow trap of VectorNormalS's `add` when x^2+y^2+z^2 >= 2^31)
-- would leave OpenBIOS halted until the hard timeout: record it with the call that caused it and end the run.
keep_exc = PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'ch28 exception', function()
  if not saved then return end
  local cause, epc, bad = 0, 0, 0
  pcall(function()
    local cp0 = R.CP0.r
    cause, epc, bad = tonumber(cp0[13]) or 0, tonumber(cp0[14]) or 0, tonumber(cp0[8]) or 0
  end)
  local code = math.floor(cause / 4) % 32
  if code == 0 or code == 8 then return end          -- an interrupt or a syscall during the call, not a fault
  cur.exception = { code = code, epc = epc % 4294967296, badvaddr = bad % 4294967296 }
  calls[#calls + 1] = cur
  verify.record('exception', cur.exception)
  saved = nil
  verify.finish('exception')
end)

keep_fd = PCSX.addBreakpoint(fd, 'Exec', 4, 'ch28 caller', function()
  if resumed then resumed = false; return end        -- the restored pc re-hits this breakpoint once
  if saved or verify.frame < 8 then return end
  idx = idx + 1
  if idx > #cases then return end
  cur = { eye = cases[idx][1], target = cases[idx][2], up = cases[idx][3] }
  for k = 0, 2 do
    verify.write_u32(ARGS + 4 * k, cur.eye[k + 1] % 4294967296)
    verify.write_u32(ARGS + 12 + 4 * k, cur.target[k + 1] % 4294967296)
    verify.write_u32(ARGS + 24 + 4 * k, cur.up[k + 1] % 4294967296)
  end
  saved = {}
  for i = 1, 31 do saved[i] = get(i) end
  saved_pc = R.pc
  sent = {}
  for i, r in ipairs({ 16, 17, 18, 19, 20, 21, 22, 23, 30 }) do
    sent[i] = 0xC0DE0000 + i * 0x101
    set(r, sent[i])
  end
  local sp = (saved[29] - 256) - ((saved[29] - 256) % 8)
  sent[10] = sp
  set(29, sp)
  set(4, ARGS); set(5, ARGS + 12); set(6, ARGS + 24)
  set(31, TRAMP)
  for _, r in ipairs({ 2, 3, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25 }) do set(r, 0x5A5A5A5A) end
  R.pc = fn
end)
