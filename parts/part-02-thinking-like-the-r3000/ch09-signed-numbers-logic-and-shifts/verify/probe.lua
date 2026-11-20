-- Chapter 9 probe: calls abs, sign_extend, popcount, rgb888_to_bgr555, bgr555_unpack and
-- swap_endian32 directly (shared helper tools/verify-lib/directcall.lua), then lets `main` run.
-- Records: seed, calls (per-call tables: fn, a0, a1, v0, v1, returned, instrs, clobbered), entries.
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd, rnd32 = DC.rnd, DC.rnd32

local calls = {}
local function call(fn, a0, a1) calls[#calls + 1] = { fn = fn, a0 = a0 % 4294967296, a1 = a1 } end

local EDGE = { 0, 1, 0xFFFFFFFF, 0x80000000, 0x7FFFFFFF, 0x80000001, 0x12345678, 0xFFFF0000,
               0x0000FFFF, 0xAAAAAAAA, 0x55555555, 0xFFFFFFFE, 0x000000FF, 0x01020304 }

for _, v in ipairs(EDGE) do
  call('abs', v); call('popcount', v); call('swap_endian32', v)
end
for _ = 1, 12 do
  local v = rnd32()
  call('abs', v); call('popcount', v); call('swap_endian32', v)
end
call('abs', 0xFFFFFFFB)   -- -5
call('abs', 5)
for _ = 1, 4 do call('popcount', 2 ^ rnd(32)) end            -- single bits
call('popcount', 0xFFFFFFFF)

-- sign_extend: every width 1..32, edge values and random garbage above the field
for bits = 1, 32 do
  local top = 2 ^ (bits - 1)
  for _, v in ipairs({ 0, 0xFFFFFFFF, top, top - 1, 0x80000000, 0x7FFFFFFF }) do
    call('sign_extend', v, bits)
  end
  call('sign_extend', rnd32(), bits)
  call('sign_extend', rnd32(), bits)
end

local COLORS = { 0, 0xFFFFFF, 0xFF0000, 0x00FF00, 0x0000FF, 0x070707, 0x080808, 0xF8F8F8,
                 0xFFFFFFFF, 0x00FF8040, 0xFF123456, 0x010203 }
for _, v in ipairs(COLORS) do call('rgb888_to_bgr555', v) end
for _ = 1, 16 do call('rgb888_to_bgr555', rnd32()) end

local PIX = { 0, 0x7FFF, 0x8000, 0xFFFF, 0x001F, 0x03E0, 0x7C00, 0x0001, 0xABCD1234, 0xFFFF0000,
              0x1234C3A5, 0x00008421 }
for _, v in ipairs(PIX) do call('bgr555_unpack', v) end
for _ = 1, 16 do call('bgr555_unpack', rnd32()) end

local ROUTINES = { 'abs', 'sign_extend', 'popcount', 'rgb888_to_bgr555', 'bgr555_unpack', 'swap_endian32' }
local d = DC.new{ calls = calls, routines = ROUTINES, limit = 2000 }

verify.on_exec('done', function()
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
end)
_G.ch09_keep = d.keep
