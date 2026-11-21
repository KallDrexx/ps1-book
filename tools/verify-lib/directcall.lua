-- directcall.lua -- shared helper: call the reader's subroutines DIRECTLY from the probe.
-- Usage (inside a chapter probe.lua):
--   local DC = dofile(verify.libdir .. '/directcall.lua')     -- seeds math.random; DC.seed is printed on failure
--   local calls = { {fn='abs', a0=5}, ... }                   -- build with DC.rnd(n), DC.rnd32()
--   local d = DC.new{ calls = calls, routines = {'abs', ...}, limit = 4000 }
-- Each call: { fn='name', a0=,a1=,a2=,a3=, prepare=function(c) (optional, runs first),
--   check=function(c, rec) (optional, may add fields to the record), ...other fields copied to the record }.
-- Phase 1 starts when `main` is first reached: for every call it seeds callee-saved registers
-- ($s0-$s7,$gp,$sp,$fp) with sentinels, scribbles caller-saved ones, aims $ra at a trampoline
-- (`j TRAMP`) and sets the PC to the routine. When the trampoline is reached (or `limit`
-- instructions pass) a record is stored. Phase 2 restores the registers and lets `main` run.
-- d.records: list of {fn, a0..a3, v0, v1, returned, instrs, clobbered={names}, ...}
-- d.entries[name]: times each routine was entered during phase 2 (the real driver run).
-- CPU exceptions (the BIOS vector 0x80000080; interrupts ignored) would leave OpenBIOS halted until the hard
-- timeout, so the run ends at once instead. In phase 1 the faulting call is first recorded (returned = false,
-- exception = {code, epc, badvaddr, phase, fn}). Then o.on_exception(info) is called if given (it must finish
-- the run); otherwise seed/calls/entries/exception are recorded and the run ends with status 'exception'.
-- (Resuming with the next call after an exception proved unreliable in PCSX-Redux, so it is not attempted.)
-- Optional extras (used by Chapter 10): a call may carry its own `limit` (instructions); DC.SP = the $sp given to
-- every direct call; d.cur = the call in progress; o.on_step(c) is called before every instruction executed in
-- phase 1; d.main_sp = $sp as it was when `main` was first reached.
local DC = {}
local R = PCSX.getRegisters()
local GPR = R.GPR.r
local NAMES = { 'zero','at','v0','v1','a0','a1','a2','a3','t0','t1','t2','t3','t4','t5','t6','t7',
                's0','s1','s2','s3','s4','s5','s6','s7','t8','t9','k0','k1','gp','sp','fp','ra' }
local IDX = {}
for i, n in ipairs(NAMES) do IDX[n] = i - 1 end
local CALLEE = { 's0','s1','s2','s3','s4','s5','s6','s7','gp','sp','fp' }
local GARBAGE = { 'at','v0','v1','a0','a1','a2','a3','t0','t1','t2','t3','t4','t5','t6','t7','t8','t9' }
local TRAMP, SP = 0x80090000, 0x801F0000

local function regget(i) return tonumber(GPR[i]) % 4294967296 end
local function regset(i, v) GPR[i] = v % 4294967296 end

DC.regget, DC.regset, DC.IDX, DC.SP = regget, regset, IDX, SP
DC.seed = tonumber(os.time()) % 100000
math.randomseed(DC.seed)
function DC.rnd(n) return math.random(0, n - 1) end
function DC.rnd32() return math.random(0, 65535) * 65536 + math.random(0, 65535) end

function DC.new(o)
  local d = { records = {}, entries = {}, phase = 1, seed = DC.seed }
  local calls, limit = o.calls, o.limit or 4000
  local idx, saved, count = 0, nil, 0
  local main_addr = verify.resolve('main')
  d.keep = {}
  local keepers = d.keep

  local function prepare(c)
    d.cur = c
    verify.write_u32(TRAMP, 0x08000000 + math.floor((TRAMP % 0x10000000) / 4))   -- j TRAMP
    verify.write_u32(TRAMP + 4, 0)                                                 -- nop
    if c.prepare then c.prepare(c) end
    for i = 1, 31 do regset(i, 0) end
    for _, n in ipairs(GARBAGE) do regset(IDX[n], DC.rnd32()) end
    c.sent = {}
    for i, n in ipairs(CALLEE) do
      local v = 0xC0DE0000 + i * 0x101
      if n == 'sp' then v = SP end
      if n == 'gp' and saved and saved[IDX.gp] ~= 0 then v = saved[IDX.gp] end   -- a GPREL (SDK) program addresses small globals through $gp: keep its real value
      regset(IDX[n], v); c.sent[n] = v
    end
    for _, a in ipairs({ 'a0','a1','a2','a3' }) do
      if c[a] ~= nil then regset(IDX[a], c[a]) end
    end
    regset(IDX.ra, TRAMP)
    R.pc = verify.resolve(c.fn)
    count = 0
  end

  local function finish_call(c, aborted)
    local rec = { returned = not aborted, instrs = count, v0 = regget(IDX.v0), v1 = regget(IDX.v1),
                  clobbered = {} }
    for k, v in pairs(c) do
      if type(v) ~= 'function' and k ~= 'sent' then rec[k] = v end
    end
    for _, n in ipairs(CALLEE) do
      if regget(IDX[n]) ~= c.sent[n] then rec.clobbered[#rec.clobbered + 1] = n end
    end
    if c.check then c.check(c, rec) end
    d.records[#d.records + 1] = rec
  end

  local function restore()
    for i = 1, 31 do regset(i, saved[i]) end
    d.main_sp = saved[IDX.sp]
    R.pc = main_addr
    d.phase = 2
  end

  local function next_call()
    idx = idx + 1
    if idx > #calls then restore(); return end
    prepare(calls[idx])
  end

  keepers[#keepers + 1] = PCSX.addBreakpoint(TRAMP, 'Exec', 4, 'verify tramp', function()
    if d.phase ~= 1 then return end
    finish_call(calls[idx], false)
    next_call()
  end)
  keepers[#keepers + 1] = PCSX.addBreakpoint(0x80010000, 'Exec', 0x20000, 'verify limit', function()
    if d.phase ~= 1 then return false end
    if o.on_step and calls[idx] then o.on_step(calls[idx]) end
    count = count + 1
    if count > ((calls[idx] and calls[idx].limit) or limit) then finish_call(calls[idx], true); next_call() end
  end)
  keepers[#keepers + 1] = PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
    if not saved or d.ended then return end
    local cause, epc, bad = 0, 0, 0
    pcall(function()
      local cp0 = R.CP0.r
      cause, epc, bad = tonumber(cp0[13]) or 0, tonumber(cp0[14]) or 0, tonumber(cp0[8]) or 0
    end)
    local code = math.floor(cause / 4) % 32
    if code == 0 then return end                                   -- an interrupt, not a fault
    if code == 8 and d.phase ~= 1 then return end                  -- a syscall from the SDK (EnterCriticalSection) after main, not a fault
    d.ended = true
    local c = d.phase == 1 and calls[idx] or nil
    local info = { code = code, epc = epc % 4294967296, badvaddr = bad % 4294967296, phase = d.phase,
                   fn = c and c.fn or '' }
    if c then c.exception = info; finish_call(c, true) end
    if o.on_exception then
      o.on_exception(info)
    else
      verify.record('seed', DC.seed)
      verify.record('calls', d.records)
      verify.record('entries', d.entries)
      verify.record('exception', info)
      verify.finish('exception')
    end
    return false
  end)
  for _, name in ipairs(o.routines or {}) do
    d.entries[name] = 0
    local a = verify.sym[name]
    if a then
      keepers[#keepers + 1] = PCSX.addBreakpoint(a, 'Exec', 4, 'verify entry', function()
        if d.phase == 2 then d.entries[name] = d.entries[name] + 1 end
      end)
    end
  end
  keepers[#keepers + 1] = PCSX.addBreakpoint(main_addr, 'Exec', 4, 'verify main', function()
    if d.phase ~= 1 or saved then return end
    saved = {}
    for i = 1, 31 do saved[i] = regget(i) end
    for _, name in ipairs(o.routines or {}) do
      if not verify.sym[name] then d.phase = 2; return end
    end
    next_call()
  end)
  return d
end

return DC
