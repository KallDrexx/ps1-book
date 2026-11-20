-- Chapter 10 probe. Phase 1: calls factorial, fibonacci and sum6 DIRECTLY (tools/verify-lib/directcall.lua)
-- with sentinel-seeded callee-saved registers, garbage temporaries, $ra aimed at a trampoline and, for sum6,
-- the 5th/6th arguments placed at 16($sp)/20($sp) with decoys around them.
-- While a routine runs it records: the lowest $sp reached, every re-entry of the routine (its $sp must be
-- 8-aligned; the gap to the enclosing entry is that routine's frame size) and the number of re-entries.
-- On every re-entry it also scribbles over the re-entered callee's home area [$sp, $sp+16) (reserved for it by its
-- caller) and over the 64 bytes below $sp, exactly what a legitimate callee is allowed to do. The values are
-- word-aligned addresses outside the program, so a jump through a clobbered $ra faults or runs away quickly;
-- directcall.lua ends the run at the first CPU exception.
-- Phase 2: the real driver runs; records $sp at `main`, at `done`, the lowest $sp reached, and what was on
-- the stack when `sum6` was entered.
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd, rnd32 = DC.rnd, DC.rnd32
local SP, ISP = DC.SP, DC.IDX.sp


local calls = {}
local function reset(c)
  c.min_sp, c.nested, c.fmin, c.fmax, c.misaligned = SP, 0, 1e9, 0, 0
  c.stk = {}
end
local function fib(n) local a, b = 0, 1; for _ = 1, n do a, b = b, a + b end; return a end
local aborted = 0       -- calls that never returned; once there are two, later calls get a small limit (a broken
                        -- routine must not make the whole probe time out)
local function add(c)
  -- instruction limit per call: the 80-instructions-per-entry budget (checks.py) plus slack
  local entries = (c.fn == 'factorial' and math.max(c.a0, 1)) or (c.fn == 'fibonacci' and 2 * fib(c.a0 + 1)) or 1
  c.limit = 80 * entries + 200
  local u = c.prepare
  c.prepare = function(cc)
    reset(cc)
    if aborted >= 2 then cc.limit = math.min(cc.limit, 3000) end
    if u then u(cc) end
  end
  c.check = function(cc, rec) if not rec.returned then aborted = aborted + 1 end end
  calls[#calls + 1] = c
end

for _, n in ipairs({ 0, 1, 2, 3, 4, 5, 6, 10, 12, 13, 20, 33, 100 }) do add({ fn = 'factorial', a0 = n }) end
for _ = 1, 4 do add({ fn = 'factorial', a0 = 2 + rnd(24) }) end
for _, n in ipairs({ 0, 1, 2, 3, 4, 5, 7, 10, 15 }) do add({ fn = 'fibonacci', a0 = n }) end
for _ = 1, 3 do add({ fn = 'fibonacci', a0 = 2 + rnd(12) }) end

local function sum6(a, b, c, d, e, f)
  add({ fn = 'sum6', a0 = a, a1 = b, a2 = c, a3 = d, e = e, f = f,
        prepare = function(cc)
          for i = 0, 12, 4 do verify.write_u32(SP + i, 0xBAD00000 + i) end      -- home area: junk
          verify.write_u32(SP + 16, cc.e)
          verify.write_u32(SP + 20, cc.f)
          for i = 24, 60, 4 do verify.write_u32(SP + i, 0xBADBAD00 + i) end      -- above the arguments: junk
        end })
end
sum6(1, 2, 3, 4, 5, 6)
sum6(10, 20, 30, 40, 50, 60)
sum6(0, 0, 0, 0, 0, 1)
sum6(0, 0, 0, 0, 1, 0)
sum6(0xFFFFFFFF, 0, 0, 0, 0, 0)
sum6(0x80000000, 0x80000000, 0, 0, 7, 0)
for _ = 1, 8 do sum6(rnd32(), rnd32(), rnd32(), rnd32(), rnd32(), rnd32()) end

local ROUTINES = { 'factorial', 'fibonacci', 'sum6' }
local d  -- set below
local p2 = { min_sp = 0xFFFFFFFF }
local dump
d = DC.new{ calls = calls, routines = ROUTINES, limit = 120000,
  -- a CPU exception in phase 1 aborts that call (rec.exception); one in the driver run ends the run here
  on_exception = function(info) p2.crash = info; dump(); verify.finish('crash') end,
  on_step = function(c)
    local sp = DC.regget(ISP)
    if sp < c.min_sp then c.min_sp = sp end
  end }

-- re-entries of the routine being tested (phase 1 only)
local keep = {}
for _, name in ipairs({ 'factorial', 'fibonacci' }) do
  local a = verify.sym[name]
  if a then
    keep[#keep + 1] = PCSX.addBreakpoint(a, 'Exec', 4, 'ch10 entry', function()
      if d.phase ~= 1 then return end
      local c = d.cur
      if not c or c.fn ~= name then return end
      local sp = DC.regget(ISP)
      if sp >= SP then return end                      -- the direct call itself, not a re-entry
      c.nested = c.nested + 1
      if sp % 8 ~= 0 and c.misaligned == 0 then c.misaligned = sp end
      local stk = c.stk
      while #stk > 0 and stk[#stk] <= sp do stk[#stk] = nil end
      local parent = stk[#stk] or SP                   -- the enclosing entry (the harness for the first)
      local frame = parent - sp
      if frame < c.fmin then c.fmin = frame end
      if frame > c.fmax then c.fmax = frame end
      stk[#stk + 1] = sp
      for i = 0, 12, 4 do verify.write_u32(sp + i, 0x80040000 + i) end   -- the callee's home area
      for i = 4, 64, 4 do verify.write_u32(sp - i, 0x80041000 + i) end   -- below $sp: not yours any more
    end)
  end
end

-- phase 2: lowest $sp of the real run, and sum6's arguments as the driver left them
local p2_steps = 0
local wild = 0
local function p2_step()
  if d.phase == 1 then          -- a direct call that ran off into the weeds never reaches the limit counter
    local pc = tonumber(PCSX.getRegisters().pc) % 4294967296
    if (pc < 0x80010000 or pc >= 0x80030000) and not (pc >= 0x80090000 and pc < 0x80090008) then
      wild = wild + 1
      if wild > 50000 then
        p2.crash = { code = -1, epc = pc, badvaddr = 0, phase = 1, fn = d.cur and d.cur.fn or '' }
        dump_on_hang(); verify.finish('crash'); return false
      end
    end
    return
  end
  if d.phase ~= 2 then return end
  p2_steps = p2_steps + 1
  if p2_steps > 300000 then dump_on_hang(); verify.finish('hang'); return false end     -- the real run needs ~50k; this is a hang
  local sp = DC.regget(ISP)
  if sp < p2.min_sp then p2.min_sp = sp end
end
-- all three views of RAM: wild jumps often land in KUSEG / KSEG1 (a runaway there is a hang too)
for _, base in ipairs({ 0x80000000, 0x00000000, 0xA0000000 }) do
  keep[#keep + 1] = PCSX.addBreakpoint(base, 'Exec', 0x200000, 'ch10 sp', p2_step)
end
if verify.sym.sum6 then
  keep[#keep + 1] = PCSX.addBreakpoint(verify.sym.sum6, 'Exec', 4, 'ch10 sum6', function()
    if d.phase ~= 2 or p2.sum6 then return end
    local sp = DC.regget(ISP)
    p2.sum6 = { sp = sp, e = verify.u32(sp + 16), f = verify.u32(sp + 20),
                a0 = DC.regget(4), a1 = DC.regget(5), a2 = DC.regget(6), a3 = DC.regget(7) }
  end)
end

function dump()
  p2.done_sp = DC.regget(ISP)
  p2.main_sp = d.main_sp
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
  verify.record('phase2', p2)
end
dump_on_hang = dump
verify.on_exec('done', dump)

_G.ch10_keep = { d.keep, keep }
