-- Chapter 8 probe: calls factorial, sum_array and max_array directly (shared helper
-- tools/verify-lib/directcall.lua), then lets `main` run for real.
-- Array calls get a scratch array at ARR with poisoned guard words; `mem_intact` records
-- whether the routine left the array and its surroundings untouched.
-- Records: seed, calls (fn, a0, a1, len, vals, v0, returned, instrs, clobbered, mem_intact), entries.
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd, rnd32 = DC.rnd, DC.rnd32
local function signed(v) if v >= 2147483648 then return v - 4294967296 end return v end

local ARR = 0x80080000         -- scratch arrays live here (well past the program)
local function put(addr, v) verify.write_u32(addr, v % 4294967296) end

local function prep_array(c)
  for k = -8, 80 do put(ARR + 4 * k, 0xA5A5A5A5) end
  for i, v in ipairs(c.vals) do put(ARR + 4 * (i - 1), v) end
  c.a0, c.a1 = ARR, c.len
end

local function check_array(c, rec)
  local ok = true
  for i, v in ipairs(c.vals) do
    if verify.u32(ARR + 4 * (i - 1)) ~= v % 4294967296 then ok = false end
  end
  for k = -8, -1 do if verify.u32(ARR + 4 * k) ~= 0xA5A5A5A5 then ok = false end end
  for k = #c.vals, 80 do if verify.u32(ARR + 4 * k) ~= 0xA5A5A5A5 then ok = false end end
  rec.mem_intact = ok
end

local calls = {}
local function fact(n) calls[#calls + 1] = { fn = 'factorial', a0 = n } end
local function arr(fn, vals, len)
  calls[#calls + 1] = { fn = fn, vals = vals, len = len or #vals, prepare = prep_array, check = check_array }
end
local function rand_vals(n, f)
  local v = {}
  for i = 1, n do v[i] = f() end
  return v
end
local function mixed() if rnd(3) == 0 then return signed(rnd32()) end return rnd(2001) - 1000 end

for _, n in ipairs({ 5, 0, 1, 2, 12, 13, 20 }) do fact(n) end
for _ = 1, 4 do fact(rnd(21)) end
arr('sum_array', { 0x5A5A5A5A, 0x5A5A5A5A }, 0)               -- len 0: must read nothing
arr('sum_array', { 41 })
arr('sum_array', { -7 })
arr('sum_array', { 0x7FFFFFFF, 1 })                            -- wraps
for _ = 1, 4 do arr('sum_array', rand_vals(2 + rnd(24), mixed)) end
arr('max_array', { -5 })
arr('max_array', { -9, -2, -7, -300 })                         -- all negative
arr('max_array', { -1, -2, -3 })                               -- max first
arr('max_array', { -3, -2, -1 })                               -- max last
arr('max_array', { 0, -2147483648, 2147483647, 5 })            -- extremes (signed compare)
arr('max_array', { 1, -2147483648 })
for _ = 1, 4 do arr('max_array', rand_vals(1 + rnd(24), mixed)) end
for _ = 1, 2 do arr('max_array', rand_vals(1 + rnd(12), function() return -1 - rnd(100000) end)) end

local d = DC.new{ calls = calls, routines = { 'factorial', 'sum_array', 'max_array' }, limit = 4000 }

verify.on_exec('done', function()
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
end)
_G.ch08_keep = d.keep
