-- Chapter 12 probe: calls my_memcpy / my_memset / my_strlen / the mulK routines / udiv10 and the byte-wise
-- baselines directly (tools/verify-lib/directcall.lua), with guard bytes around every buffer, then lets `main` run.
-- Each record carries `instrs` (instructions executed, delay slots included) and, for the buffer routines,
-- `out` (hex of the destination), `src_hex`, `guard_ok`, `in_ok`. Python computes the expectations.
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd, rnd32 = DC.rnd, DC.rnd32

local SRC = 0x80080100      -- source area (call-specific offset 0..3 added)
local DST = 0x80084100      -- destination area
local GUARD = 16

local function w8(a, v) verify.write_u8(a, v % 256) end
local function fill(a, n, v) for i = 0, n - 1 do w8(a + i, v) end end
local function hex(a, n)
  local s = verify.read_bytes(a, n)
  local t = {}
  for i = 1, #s do t[i] = string.format('%02x', s:byte(i)) end
  return table.concat(t)
end
local function guards_ok(a, n)      -- GUARD bytes before a and after a+n are still 0xA5
  for i = 1, GUARD do
    if verify.u8(a - i) ~= 0xA5 or verify.u8(a + n + i - 1) ~= 0xA5 then return false end
  end
  return true
end
local EDGE8 = { 0, 1, 0x7F, 0x80, 0x81, 0xFF }
local function byte(mode)
  if mode == 'edge' and rnd(3) == 0 then return EDGE8[1 + rnd(#EDGE8)] end
  return rnd(256)
end

local calls = {}

local function memcpy(fn, n, so, dof, budget)
  calls[#calls + 1] = { fn = fn, kind = 'memcpy', n = n, so = so, dof = dof, budget = budget, limit = 20000,
    prepare = function(c)
      fill(DST - GUARD - 4, 1100 + 2 * GUARD + 8, 0xA5)
      fill(SRC - GUARD - 4, 1100 + 2 * GUARD + 8, 0xA5)
      local t = {}
      for i = 0, n - 1 do local b = byte('edge'); w8(SRC + so + i, b); t[#t + 1] = string.format('%02x', b) end
      c.src_hex = table.concat(t)
      c.a0, c.a1, c.a2 = DST + dof, SRC + so, n
      c.dst = DST + dof
    end,
    check = function(c, rec)
      rec.out = hex(DST + dof, n)
      rec.guard_ok = guards_ok(DST + dof, n)
      rec.in_ok = hex(SRC + so, n) == c.src_hex and guards_ok(SRC + so, n)
    end }
end

local function memset(fn, n, dof, val, budget)
  calls[#calls + 1] = { fn = fn, kind = 'memset', n = n, dof = dof, val = val, budget = budget, limit = 20000,
    prepare = function(c)
      fill(DST - GUARD - 4, 1100 + 2 * GUARD + 8, 0xA5)
      c.a0, c.a1, c.a2 = DST + dof, val, n
      c.dst = DST + dof
    end,
    check = function(c, rec)
      rec.out = hex(DST + dof, n)
      rec.guard_ok = guards_ok(DST + dof, n)
      rec.in_ok = true
    end }
end

local function strlen(fn, len, so, budget)
  calls[#calls + 1] = { fn = fn, kind = 'strlen', n = len, so = so, budget = budget, limit = 20000,
    prepare = function(c)
      for i = 0, 1100 + 2 * GUARD do w8(SRC - GUARD + i, byte('edge')) end   -- junk everywhere (may include zeros)
      for i = 0, len - 1 do local b = byte('edge'); if b == 0 then b = 1 end; w8(SRC + so + i, b) end
      w8(SRC + so + len, 0)
      c.a0 = SRC + so
    end,
    check = function(c, rec) rec.in_ok = true; rec.guard_ok = true end }
end

local LENS = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 15, 16, 17, 31, 33, 100, 255, 257 }
-- memcpy: all 16 alignment pairs at one length, then many lengths
for so = 0, 3 do for d = 0, 3 do memcpy('my_memcpy', 37, so, d) end end
for _, n in ipairs(LENS) do memcpy('my_memcpy', n, rnd(4), rnd(4)) end
for _, n in ipairs(LENS) do local a = rnd(4); memcpy('my_memcpy', n, a, a) end
memcpy('my_memcpy', 1024, 0, 0, true)
memcpy('my_memcpy', 1023, 1, 1, true)
memcpy('my_memcpy', 1000, 3, 3, true)
memcpy('my_memcpy', 999, 1, 2)
memcpy('bytes_memcpy', 1024, 0, 0)

-- memset
local VALS = { 0, 0xAB, 0x1234FF80, 0xFF, 0xFFFFFF00 + 7 }
for d = 0, 3 do memset('my_memset', 37, d, VALS[1 + rnd(#VALS)]) end
for _, n in ipairs(LENS) do memset('my_memset', n, rnd(4), VALS[1 + rnd(#VALS)]) end
for i = 1, #VALS do memset('my_memset', 21, i % 4, VALS[i]) end
memset('my_memset', 1024, 0, 0x1234FF80, true)
memset('my_memset', 1023, 1, 0xAB, true)
memset('my_memset', 1000, 3, 0x77, true)
memset('bytes_memset', 1024, 0, 0x5A)

-- strlen
for _, n in ipairs(LENS) do strlen('my_strlen', n, rnd(4)) end
for so = 0, 3 do strlen('my_strlen', 40, so) end
strlen('my_strlen', 1000, 0, true)
strlen('my_strlen', 1000, 2, true)
strlen('bytes_strlen', 1000, 0)

-- multiplies and the divide
local X = { 0, 1, 2, 3, 0xFFFFFFFF, 0xFFFFFFFE, 0x7FFFFFFF, 0x80000000, 0x80000001, 320, 1024, 65536, 0xFFFF }
local MULS = { 'mul320', 'mul1024', 'mul10', 'mul100', 'mul_m5', 'mul1000', 'mul65537' }
for _, fn in ipairs(MULS) do
  for _, x in ipairs(X) do calls[#calls + 1] = { fn = fn, kind = 'mul', x = x, a0 = x, limit = 200 } end
  for _ = 1, 6 do local x = rnd32(); calls[#calls + 1] = { fn = fn, kind = 'mul', x = x, a0 = x, limit = 200 } end
end
local DIVX = { 0, 1, 9, 10, 11, 19, 20, 99, 100, 101, 65535, 65536, 999999999, 1000000000, 0x7FFFFFFF, 0x80000000,
               0xFFFFFFF0, 0xFFFFFFF9, 0xFFFFFFFA, 0xFFFFFFFB, 0xFFFFFFFE, 0xFFFFFFFF, 0xCCCCCCCC, 0xCCCCCCCD, 429496729, 429496730 }
for _, x in ipairs(DIVX) do calls[#calls + 1] = { fn = 'udiv10', kind = 'udiv', x = x, a0 = x, limit = 400 } end
for _ = 1, 40 do local x = rnd32(); calls[#calls + 1] = { fn = 'udiv10', kind = 'udiv', x = x, a0 = x, limit = 400 } end
for _ = 1, 20 do local x = rnd(100000); calls[#calls + 1] = { fn = 'udiv10', kind = 'udiv', x = x, a0 = x, limit = 400 } end

local ROUTINES = { 'my_memcpy', 'my_memset', 'my_strlen', 'mul320', 'mul1024', 'mul10', 'mul100', 'mul_m5',
                   'mul1000', 'mul65537', 'udiv10', 'bytes_memcpy', 'bytes_memset', 'bytes_strlen' }
-- Watch the multiply/divide unit on the instructions each call actually EXECUTES (so code hidden behind a jump
-- is seen too): c.md_used = "multu,mfhi," etc.; c.hazard = address of a mult/div/mthi/mtlo executed within two
-- instructions after an mfhi/mflo (the MIPS I rule, section 5.4).
local REGS = PCSX.getRegisters()
local MD = { [0x10] = 'mfhi', [0x11] = 'mthi', [0x12] = 'mflo', [0x13] = 'mtlo',
             [0x18] = 'mult', [0x19] = 'multu', [0x1A] = 'div', [0x1B] = 'divu' }
local WRITES_HILO = { mult = true, multu = true, div = true, divu = true, mthi = true, mtlo = true }
local function on_step(c)
  local pc = tonumber(REGS.pc) % 4294967296
  local w = verify.u32(pc)
  c.since_move = (c.since_move or 99) + 1
  if w >= 0x04000000 then return end                  -- not a SPECIAL (opcode 0) instruction
  local n = MD[w % 64]
  if not n then return end
  local used = c.md_used or ''
  if not used:find(n .. ',', 1, true) then c.md_used = used .. n .. ',' end
  if WRITES_HILO[n] and c.since_move <= 2 and not c.hazard then c.hazard = pc end
  if n == 'mfhi' or n == 'mflo' then c.since_move = 0 end
end

local d = DC.new{ calls = calls, routines = ROUTINES, limit = 3000, on_step = on_step }

verify.on_exec('done', function()
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
end)
_G.ch12_keep = d.keep
