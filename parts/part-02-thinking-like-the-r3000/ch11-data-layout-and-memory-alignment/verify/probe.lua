-- Chapter 11 probe: calls vt_translate, vt_bbox, vt_pack and vt_unpack directly (tools/verify-lib/directcall.lua)
-- on scratch buffers in free RAM, each surrounded by guard bytes, then lets `main` run.
-- Every call records `out` (the bytes the routine produced, as a hex string), `guard_ok` (nothing outside the
-- output area was touched) and `in_ok` (the input was not modified, where it must not be).
-- A misaligned lh/lw/sh/sw raises a CPU exception: directcall.lua stops the run and reports it.
-- Records: seed, calls, entries.
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd, rnd32 = DC.rnd, DC.rnd32

local TAB = 0x80080000      -- the SVECTOR table (8-aligned)
local OFS = 0x80083000      -- the offset SVECTOR
local OUT = 0x80084000      -- bbox output / packed buffer
local DST = 0x80085000      -- unpack destination table
local GUARD = 16

local function w8(a, v) verify.write_u8(a, v % 256) end
local function w16(a, v) w8(a, v); w8(a + 1, math.floor(v / 256)) end
local function fill(a, n, v) for i = 0, n - 1 do w8(a + i, v) end end
local function hex(a, n)
  local s = verify.read_bytes(a, n)
  local t = {}
  for i = 1, #s do t[i] = string.format('%02x', s:byte(i)) end
  return table.concat(t)
end
local function guards_ok(a, n, g)   -- the g bytes before a and after a+n are still 0xA5
  for i = 1, g do
    if verify.u8(a - i) ~= 0xA5 or verify.u8(a + n + i - 1) ~= 0xA5 then return false end
  end
  return true
end

local EDGE16 = { 0, 1, 65535, 32767, 32768, 32769, 100, 65436, 255, 256 }
local function r16(mode)
  if mode == 'edge' and rnd(2) == 0 then return EDGE16[1 + rnd(#EDGE16)] end
  return rnd(65536)
end

local calls = {}

-- ---- vt_translate ------------------------------------------------------------
local function translate(n, off, mode)
  local tab = {}
  for i = 1, 4 * n do tab[i] = r16(mode) end
  calls[#calls + 1] = { fn = 'vt_translate', n = n, tab = tab, off = off,
    prepare = function(c)
      fill(TAB - GUARD, 8 * n + 2 * GUARD, 0xA5)
      for i, v in ipairs(c.tab) do w16(TAB + 2 * (i - 1), v) end
      for i, v in ipairs(c.off) do w16(OFS + 2 * (i - 1), v) end
      c.a0, c.a1, c.a2 = TAB, n, OFS
    end,
    check = function(c, rec)
      rec.out = hex(TAB, 8 * n)
      rec.guard_ok = guards_ok(TAB, 8 * n, GUARD)
      rec.in_ok = hex(OFS, 8) == string.format('%02x%02x%02x%02x%02x%02x%02x%02x',
        c.off[1] % 256, math.floor(c.off[1] / 256), c.off[2] % 256, math.floor(c.off[2] / 256),
        c.off[3] % 256, math.floor(c.off[3] / 256), c.off[4] % 256, math.floor(c.off[4] / 256))
    end }
end
translate(8, { 10, 65516, 30, 7 })
translate(1, { 0, 0, 0, 0 })
translate(0, { 5, 5, 5, 0 })
translate(3, { 1, 1, 1, 0 }, 'edge')
translate(3, { 65535, 65535, 65535, 0 }, 'edge')
translate(4, { 32767, 32768, 32767, 0 }, 'edge')
translate(16, { 32768, 32768, 32768, 0 }, 'edge')
for _ = 1, 6 do translate(1 + rnd(16), { r16('edge'), r16('edge'), r16('edge'), rnd(65536) }, 'edge') end

-- ---- vt_bbox -----------------------------------------------------------------
local function bbox(n, gen)
  local tab = {}
  for i = 1, n do
    local v = gen(i)
    tab[#tab + 1] = v[1]; tab[#tab + 1] = v[2]; tab[#tab + 1] = v[3]; tab[#tab + 1] = rnd(65536)
  end
  calls[#calls + 1] = { fn = 'vt_bbox', n = n, tab = tab,
    prepare = function(c)
      fill(TAB - GUARD, 8 * n + 2 * GUARD, 0xA5)
      fill(OUT - GUARD, 12 + 2 * GUARD, 0xA5)
      for i, v in ipairs(c.tab) do w16(TAB + 2 * (i - 1), v) end
      c.a0, c.a1, c.a2 = TAB, n, OUT
    end,
    check = function(c, rec)
      rec.out = hex(OUT, 12)
      rec.guard_ok = guards_ok(OUT, 12, GUARD)
      rec.in_ok = hex(TAB, 8 * n) == (function()
        local t = {}
        for _, v in ipairs(c.tab) do t[#t + 1] = string.format('%02x%02x', v % 256, math.floor(v / 256)) end
        return table.concat(t)
      end)()
    end }
end
local function s16(v) return (v + 65536) % 65536 end
bbox(8, function(i) return { s16((i % 2 == 1) and -100 or 100), s16((math.floor((i - 1) / 2) % 2 == 0) and -100 or 100),
                             s16((i <= 4) and -100 or 100) } end)
bbox(1, function() return { s16(-5), 7, s16(-32768) } end)
bbox(2, function(i) if i == 1 then return { 1, 2, 3 } end return { s16(-1), s16(-2), s16(-3) } end)      -- unsigned order != signed order
bbox(4, function(i) return { s16(-i * 1000), s16(-1), s16(-30000 - i) } end)                            -- all negative
bbox(5, function(i) return { 32767, 0, 0 } end)                                                           -- all equal x
bbox(3, function(i) local e = { { 32767, 32768, 0 }, { 32768, 32767, 65535 }, { 0, 0, 32767 } } return e[i] end)
bbox(16, function() return { r16('edge'), r16('edge'), r16('edge') } end)
for _ = 1, 8 do local n = 1 + rnd(16); bbox(n, function() return { r16(), r16(), r16() } end) end
for _ = 1, 3 do local n = 1 + rnd(16); bbox(n, function() return { r16('edge'), r16('edge'), r16('edge') } end) end

-- ---- vt_pack -----------------------------------------------------------------
local function pack(n, off)
  local tab = {}
  for i = 1, 4 * n do tab[i] = rnd(65536) end
  calls[#calls + 1] = { fn = 'vt_pack', n = n, tab = tab, off = off,
    prepare = function(c)
      fill(TAB - GUARD, 8 * n + 2 * GUARD, 0xA5)
      fill(OUT - GUARD - 4, 6 * 16 + 2 * GUARD + 8, 0xA5)
      for i, v in ipairs(c.tab) do w16(TAB + 2 * (i - 1), v) end
      c.a0, c.a1, c.a2 = TAB, n, OUT + off
    end,
    check = function(c, rec)
      rec.out = hex(OUT + off, 6 * n)
      rec.guard_ok = guards_ok(OUT + off, 6 * n, GUARD)
      local t = {}
      for _, v in ipairs(c.tab) do t[#t + 1] = string.format('%02x%02x', v % 256, math.floor(v / 256)) end
      rec.in_ok = hex(TAB, 8 * n) == table.concat(t)
    end }
end
pack(8, 1)
pack(8, 0)
pack(1, 1)
pack(0, 3)
pack(2, 2)
pack(3, 3)
for off = 0, 3 do pack(5, off) end
for _ = 1, 6 do pack(1 + rnd(16), rnd(4)) end

-- ---- vt_unpack ---------------------------------------------------------------
local function unpack(n, off)
  local bytes = {}
  for i = 1, 6 * n do bytes[i] = rnd(256) end
  calls[#calls + 1] = { fn = 'vt_unpack', n = n, bytes = bytes, off = off,
    prepare = function(c)
      fill(OUT - GUARD - 4, 6 * 16 + 2 * GUARD + 8, rnd(256))      -- random junk around (and after) the packed data
      for i, v in ipairs(c.bytes) do w8(OUT + off + i - 1, v) end
      fill(DST - GUARD, 8 * n + 2 * GUARD, 0xA5)
      c.a0, c.a1, c.a2 = OUT + off, n, DST
    end,
    check = function(c, rec)
      rec.out = hex(DST, 8 * n)
      rec.guard_ok = guards_ok(DST, 8 * n, GUARD)
      local t = {}
      for _, v in ipairs(c.bytes) do t[#t + 1] = string.format('%02x', v) end
      rec.in_ok = hex(OUT + off, 6 * n) == table.concat(t)
    end }
end
unpack(8, 1)
unpack(8, 0)
unpack(1, 3)
unpack(0, 2)
unpack(3, 2)
for off = 0, 3 do unpack(5, off) end
for _ = 1, 6 do unpack(1 + rnd(16), rnd(4)) end

local ROUTINES = { 'vt_translate', 'vt_bbox', 'vt_pack', 'vt_unpack' }
local d = DC.new{ calls = calls, routines = ROUTINES, limit = 3000 }

verify.on_exec('done', function()
  verify.record('seed', DC.seed)
  verify.record('calls', d.records)
  verify.record('entries', d.entries)
end)
_G.ch11_keep = d.keep
