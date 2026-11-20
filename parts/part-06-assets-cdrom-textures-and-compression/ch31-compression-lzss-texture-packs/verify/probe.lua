-- Chapter 31 probe (main and alt runs). Observes; boots from the disc image.
-- Every time the program calls frame_done() it records one row: { frame_no, load_status, prims_submitted, emu_frame, prims }, where prims is the
-- flat list of the polygons found by walking the ordering table DrawOTag was given, 23 numbers each:
--   slot, code, r, g, b, x0 y0 u0 v0, x1 y1 u1 v1, x2 y2 u2 v2, x3 y3 u3 v3, clut, tpage     (the POLY_FT4 layout)
-- At frame_no == 3: store (count, raw, raw_size, then count * 6 halfwords of Tex), tpk_raw, tpk_raw_size, and a snapshot "raw" of the
-- decompressed blob. Cycles spent between entering lzss_decode and returning from it are summed in decode_cycles / decode_calls.
-- The run ends at frame_no == 14 (a screenshot "f10" is taken at frame_no == 10).
local SHOT_AT, END_AT = 10, 14
local FRAME_SZ = 2320                                   -- OtFrame: ot[64] + prim[2048] + guard[16]

local function s16(a)
  local v = verify.u16(a)
  return v >= 32768 and v - 65536 or v
end

local rows = {}
verify.record('rows', rows)

-- a CPU exception (not an interrupt, not a SYSCALL) ends the run
PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
  local cp0 = PCSX.getRegisters().CP0.r
  local code = math.floor((tonumber(cp0[13]) or 0) / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = (tonumber(cp0[14]) or 0) % 4294967296, badvaddr = (tonumber(cp0[8]) or 0) % 4294967296 })
  verify.finish('exception')
  return false
end)

local dec_t0, dec_total, dec_calls, hooked = nil, 0, 0, {}
if verify.sym.lzss_decode then
  verify.on_exec('lzss_decode', function(r)
    dec_t0 = verify.cycles()
    dec_calls = dec_calls + 1
    local ra = r.ra
    if not hooked[ra] then
      hooked[ra] = true
      verify.on_exec(ra, function()
        if dec_t0 then dec_total = dec_total + (verify.cycles() - dec_t0); dec_t0 = nil end
        verify.record('decode_cycles', dec_total)
        verify.record('decode_calls', dec_calls)
      end)
    end
  end)
end

local pending = {}
if verify.sym.DrawOTag and verify.sym.ot_frames then
  verify.on_exec('DrawOTag', function(r)
    local base = verify.resolve('ot_frames')
    local node, prims, entry, n = r.a0, {}, 0, 0
    while n < 400 do
      local w = verify.u32(node)
      local len, nxt = bit.rshift(w, 24), bit.band(w, 0xFFFFFF)
      n = n + 1
      if len > 0 then
        local c = verify.u32(node + 4)
        prims[#prims + 1] = math.floor(((entry - base) % FRAME_SZ) / 4)
        prims[#prims + 1] = bit.rshift(c, 24)
        prims[#prims + 1] = bit.band(c, 255)
        prims[#prims + 1] = bit.band(bit.rshift(c, 8), 255)
        prims[#prims + 1] = bit.band(bit.rshift(c, 16), 255)
        for k = 0, 3 do
          local a = node + 8 + 8 * k
          prims[#prims + 1] = s16(a)
          prims[#prims + 1] = s16(a + 2)
          prims[#prims + 1] = verify.u8(a + 4)
          prims[#prims + 1] = verify.u8(a + 5)
        end
        prims[#prims + 1] = verify.u16(node + 8 + 6)      -- clut
        prims[#prims + 1] = verify.u16(node + 8 + 14)     -- tpage
      else
        entry = node
      end
      if nxt == 0xFFFFFF then break end
      node = 0x80000000 + nxt
    end
    pending = prims
  end)
end

local n_calls = 0
verify.on_exec('frame_done', function()
  n_calls = n_calls + 1
  local n = verify.s32('frame_no')
  if n == 3 then
    local st = verify.resolve('store')
    local count, raw, rawsize = verify.s32(st), verify.u32(st + 4), verify.u32(st + 8)
    local words = { count, raw, rawsize }
    for i = 0, math.min(math.max(count, 0), 255) * 6 - 1 do words[#words + 1] = verify.u16(st + 12 + 2 * i) end
    verify.record('store', words)
    local p, sz = verify.u32('tpk_raw'), verify.u32('tpk_raw_size')
    verify.record('tpk_raw', { p, sz })
    if p >= 0x80000000 and p < 0x80200000 and sz > 0 and p + sz <= 0x80200000 then verify.snapshot('raw', p, sz) end
  end
  local row = { n, verify.s32('load_status'), verify.s32('prims_submitted'), verify.frame, pending }
  pending = {}
  rows[#rows + 1] = row
  if n == SHOT_AT then verify.screenshot('f' .. n) end
  if n >= END_AT then verify.collect('done') end
end)
