-- Chapter 8 probe.
-- Phase 1 (at the first instruction of `main`): call the reader's routines DIRECTLY,
--   one call at a time. For each call it sets $a0/$a1, seeds callee-saved registers with
--   sentinels, scribbles caller-saved ones, points $ra at a return trampoline and sets the
--   PC to the routine. When the trampoline is reached it records what happened.
-- Phase 2: restore the machine and let `main` run for real; count routine entries.
-- Records: seed, calls (list of per-call tables), entries (routine -> count in phase 2).
local ffi = require('ffi')
local R = PCSX.getRegisters()
local GPR = R.GPR.r

local function regget(i) return tonumber(GPR[i]) % 4294967296 end
local function regset(i, v) GPR[i] = v end

local NAMES = { 'zero','at','v0','v1','a0','a1','a2','a3','t0','t1','t2','t3','t4','t5','t6','t7',
                's0','s1','s2','s3','s4','s5','s6','s7','t8','t9','k0','k1','gp','sp','fp','ra' }
local IDX = {}
for i, n in ipairs(NAMES) do IDX[n] = i - 1 end

local ARR   = 0x80080000       -- scratch arrays live here (well past the program)
local TRAMP = 0x80090000       -- return trampoline: `j TRAMP ; nop`
local SP    = 0x801F0000
local LIMIT = 4000             -- instructions per call before we give up
local CALLEE = { 's0','s1','s2','s3','s4','s5','s6','s7','gp','sp','fp' }

local seed = tonumber(os.time()) % 100000
math.randomseed(seed)
local function rnd(n) return math.random(0, n - 1) end   -- 0..n-1
local function rnd32() return (rnd(65536) * 65536 + rnd(65536)) % 4294967296 end
local function signed(v) if v >= 2147483648 then return v - 4294967296 end return v end

local function build_calls()
  local c = {}
  local function fact(n) c[#c + 1] = { fn = 'factorial', a0 = n } end
  local function arr(fn, vals, len)
    c[#c + 1] = { fn = fn, vals = vals, len = len or #vals }
  end
  for _, n in ipairs({ 5, 0, 1, 2, 12, 13, 20 }) do fact(n) end
  for _ = 1, 4 do fact(rnd(21)) end
  arr('sum_array', { 0x5A5A5A5A, 0x5A5A5A5A }, 0)               -- len 0: must read nothing
  arr('sum_array', { 41 })
  arr('sum_array', { -7 })
  arr('sum_array', { 0x7FFFFFFF, 1 })                            -- wraps
  for _ = 1, 4 do
    local n = 2 + rnd(24)
    local v = {}
    for i = 1, n do
      if rnd(3) == 0 then v[i] = signed(rnd32()) else v[i] = rnd(2001) - 1000 end
    end
    arr('sum_array', v)
  end
  arr('max_array', { -5 })
  arr('max_array', { -9, -2, -7, -300 })                         -- all negative
  arr('max_array', { -1, -2, -3 })                               -- max first
  arr('max_array', { -3, -2, -1 })                               -- max last
  arr('max_array', { 0, -2147483648, 2147483647, 5 })            -- extremes (signed compare)
  arr('max_array', { 1, -2147483648 })
  for _ = 1, 4 do
    local n = 1 + rnd(24)
    local v = {}
    for i = 1, n do
      if rnd(3) == 0 then v[i] = signed(rnd32()) else v[i] = rnd(2001) - 1000 end
    end
    arr('max_array', v)
  end
  for _ = 1, 2 do                                                -- all-negative random
    local n = 1 + rnd(12)
    local v = {}
    for i = 1, n do v[i] = -1 - rnd(100000) end
    arr('max_array', v)
  end
  return c
end

local calls = build_calls()
local results = {}
local idx = 0
local phase = 1
local saved = nil
local count = 0
local entries = { factorial = 0, sum_array = 0, max_array = 0 }
local main_addr = verify.resolve('main')
local keepers = {}

local function put(addr, v) verify.write_u32(addr, v % 4294967296) end

local function prepare(c)
  -- scratch array with guard words and a poisoned surrounding region
  if c.vals then
    for k = -8, 80 do put(ARR + 4 * k, 0xA5A5A5A5) end
    for i, v in ipairs(c.vals) do put(ARR + 4 * (i - 1), v) end
    c.a0 = ARR
    c.a1 = c.len
  end
  put(TRAMP, 0x08000000 + math.floor((TRAMP % 0x10000000) / 4))   -- j TRAMP
  put(TRAMP + 4, 0)                                               -- nop
  for i = 1, 31 do regset(i, 0) end
  -- caller-saved registers get garbage the routine must not depend on
  for _, n in ipairs({ 'at','v0','v1','a2','a3','t0','t1','t2','t3','t4','t5','t6','t7','t8','t9' }) do
    regset(IDX[n], rnd32())
  end
  c.sent = {}
  for i, n in ipairs(CALLEE) do
    local v = 0xC0DE0000 + i * 0x101
    if n == 'sp' then v = SP end
    regset(IDX[n], v); c.sent[n] = v
  end
  regset(IDX.a0, c.a0); regset(IDX.a1, c.a1 or rnd32())
  regset(IDX.ra, TRAMP)
  R.pc = verify.resolve(c.fn)
  count = 0
end

local function finish_call(c, aborted)
  local rec = { fn = c.fn, a0 = c.a0, a1 = c.a1, len = c.len, vals = c.vals,
                returned = not aborted, instrs = count }
  rec.v0 = regget(IDX.v0)
  rec.clobbered = {}
  for _, n in ipairs(CALLEE) do
    if regget(IDX[n]) ~= c.sent[n] then rec.clobbered[#rec.clobbered + 1] = n end
  end
  if c.vals then
    local ok = true
    for i, v in ipairs(c.vals) do
      if verify.u32(ARR + 4 * (i - 1)) ~= v % 4294967296 then ok = false end
    end
    for k = -8, -1 do if verify.u32(ARR + 4 * k) ~= 0xA5A5A5A5 then ok = false end end
    for k = #c.vals, 80 do if verify.u32(ARR + 4 * k) ~= 0xA5A5A5A5 then ok = false end end
    rec.mem_intact = ok
  end
  results[#results + 1] = rec
end

local function restore()
  for i = 1, 31 do regset(i, saved[i]) end
  R.pc = main_addr
  phase = 2
end

local function next_call()
  idx = idx + 1
  if idx > #calls then restore(); return end
  prepare(calls[idx])
end

local tramp_bp, limit_bp, entry_bps = nil, nil, {}

tramp_bp = PCSX.addBreakpoint(TRAMP, 'Exec', 4, 'verify tramp', function()
  if phase ~= 1 then return end
  finish_call(calls[idx], false)
  next_call()
end)

limit_bp = PCSX.addBreakpoint(0x80010000, 'Exec', 0x20000, 'verify limit', function()
  if phase ~= 1 then return false end   -- phase 2: remove it, so a hang hits the frame limit quickly
  count = count + 1
  if count > LIMIT then
    finish_call(calls[idx], true)
    next_call()
  end
end)

for _, name in ipairs({ 'factorial', 'sum_array', 'max_array' }) do
  local a = verify.sym[name]
  if a then
    entry_bps[#entry_bps + 1] = PCSX.addBreakpoint(a, 'Exec', 4, 'verify entry', function()
      if phase == 2 then entries[name] = entries[name] + 1 end
    end)
  end
end

-- The routines must exist; otherwise skip phase 1 (the static check reports it).
local main_bp
main_bp = PCSX.addBreakpoint(main_addr, 'Exec', 4, 'verify main', function()
  if phase ~= 1 or saved then return end
  saved = {}
  for i = 1, 31 do saved[i] = regget(i) end
  if not (verify.sym.factorial and verify.sym.sum_array and verify.sym.max_array) then
    phase = 2; return
  end
  next_call()
end)

verify.on_exec('done', function()
  verify.record('seed', seed)
  verify.record('calls', results)
  verify.record('entries', entries)
end)
_G.ch08_keep = { tramp_bp, limit_bp, entry_bps, main_bp }
