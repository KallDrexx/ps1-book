-- Chapter 23 probe.
-- (1) Direct calls (shared helper tools/verify-lib/directcall.lua): when `main` is first reached, every case of the
--     patched `tests` table is run through the reader's function DIRECTLY, with sentinels in $s0-$s7/$gp/$sp and
--     garbage in the temporaries. Records: seed, calls (fn, op, a0..a3, v0, returned, instrs, clobbered, o0/o1 for
--     fx_rotate's output struct), entries.
-- (2) The benchmark: cycles and executed instructions between entry and return of bench_float / bench_fixed during
--     the real run (the cycle counter is the emulator's; the instruction count is deterministic).
local DC = dofile(verify.libdir .. '/directcall.lua')

local N = 192
local FNS = { [0] = 'fx_from_int', 'fx_mul', 'fx_div', 'fx_lerp', 'fx_sqrt', 'fx_rotate' }
local SCRATCH = 0x801D0000                     -- fx_rotate's out struct

local calls = {}
for i = 0, N - 1 do
  calls[#calls + 1] = {
    idx = i,
    fn = 'fx_mul',
    limit = 60000,
    prepare = function(c)
      local base = verify.resolve('tests') + 16 * c.idx
      local op = verify.s32(base)
      c.op, c.fn = op, FNS[op] or 'fx_mul'
      c.a0, c.a1, c.a2, c.a3 = verify.u32(base + 4), verify.u32(base + 8), verify.u32(base + 12), nil
      if op == 5 then
        c.a2 = verify.u32(base + 12)
        c.a3 = SCRATCH
        verify.write_u32(SCRATCH, 0xDEADBEEF)
        verify.write_u32(SCRATCH + 4, 0xDEADBEEF)
      end
    end,
    check = function(c, rec)
      if c.op == 5 then
        rec.o0, rec.o1 = verify.s32(SCRATCH), verify.s32(SCRATCH + 4)
      end
    end,
  }
end

local routines = {}
for _, n in pairs(FNS) do routines[#routines + 1] = n end
local d = DC.new{ calls = calls, routines = routines, limit = 60000 }

-- ---- benchmark ---------------------------------------------------------------------------------------------------
local TEXT0, TEXT_N = 0x80010000, 0x20000
local counting, instrs = false, 0
local bench_keep = PCSX.addBreakpoint(TEXT0, 'Exec', TEXT_N, 'ch23 count', function()
  if counting then instrs = instrs + 1 end
end)

local function time_fn(name, key)
  if not verify.sym[name] then return end
  verify.on_exec(name, function(r)
    if d.phase ~= 2 then return end
    local c0, n0, ra = verify.cycles(), instrs, r.ra
    counting = true
    local stop
    stop = PCSX.addBreakpoint(ra, 'Exec', 4, 'ch23 bench end', function()
      counting = false
      verify.record(key, { cycles = verify.cycles() - c0, instrs = instrs - n0 })
      bench_stop_keep = bench_stop_keep or {}
      return false
    end)
    bench_stop_keep = bench_stop_keep or {}
    bench_stop_keep[#bench_stop_keep + 1] = stop
  end)
end
time_fn('bench_float', 'bench_float')
time_fn('bench_fixed', 'bench_fixed')

verify.on_exec('stop_here', function()
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
end)
_G.ch23_keep = { d.keep, bench_keep }
