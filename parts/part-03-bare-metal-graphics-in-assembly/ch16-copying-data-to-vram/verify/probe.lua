-- Chapter 16 probe.
-- Phase 1: gpu_init, then vram_upload(ptr, x, y, w, h) is called DIRECTLY (tools/verify-lib/directcall.lua) with
--   a random pixel buffer in RAM (junk in the pad half of the last word and in the words after it), harness-chosen
--   x/y/w/h (odd widths, odd pixel counts, the right and bottom edges), h at 16($sp), junk around it.
--   For every call the probe records
--     * the GPU transcript: every GP1 word and every GP0 word that is NOT pixel data, plus how many pixel-data
--       words followed each A0h header and how many GPUSTAT reads happened before each recorded word;
--     * a VRAM comparison done here (the probe knows the data it wrote): pixels of the rectangle that differ from the
--       buffer, and pixels OUTSIDE the rectangle that changed.
-- Phase 2: the real program runs to `done`; its whole transcript is recorded the same way ('gpu').
-- The value of a write is the source register of the `sw` at the faulting pc (decoded here), because the breakpoint
-- callback does not get it. Pixel-data words are only counted (a 24-bpp screen is 57600 words).
local DC = dofile(verify.libdir .. '/directcall.lua')
local rnd, rnd32, SP = DC.rnd, DC.rnd32, DC.SP
local ffi = require('ffi')
local GP0, GP1 = 0x1F801810, 0x1F801814
local BUF = 0x80110000

local d
local reads = 0
local MAX_WORDS2, MAX_READS2 = 90000, 400000
local function runaway(why)
  verify.record('runaway', why)
  verify.finish('runaway: ' .. why)
end

-- ---- transcript: [port, value, reads_before] ; {2, n_data_words, reads_at_last} ; {3, words_still_missing}
local function new_state() return { log = {}, hdr = 0, hw = nil, data = 0, ndata = 0, total = 0 } end
local S1, S2 = new_state(), new_state()
local function cur() return (d and d.phase == 1) and S1 or S2 end
local function reg_value(pc)
  local w = verify.u32(pc % 0x200000 + 0x80000000)
  return DC.regget(bit.band(bit.rshift(w, 16), 31))
end
local function note(port, v)
  local st = cur()
  local lg = st.log
  st.total = st.total + 1
  if port == 1 then lg[#lg + 1] = { 1, v, reads }; return end
  if st.data > 0 then
    st.data = st.data - 1; st.ndata = st.ndata + 1
    if st.data == 0 then lg[#lg + 1] = { 2, st.ndata, reads } end
    return
  end
  if #lg < 3000 then lg[#lg + 1] = { 0, v, reads } end
  if st.hdr > 0 then
    st.hdr = st.hdr - 1
    if st.hdr == 1 then st.hw = v end
    if st.hdr == 0 and st.kind == 0xA0 then
      local w, h = bit.band(v, 0x3FF), bit.band(bit.rshift(v, 16), 0x1FF)   -- psx-spx: size 0 = max
      if w == 0 then w = 1024 end
      if h == 0 then h = 512 end
      st.data, st.ndata = math.floor((w * h + 1) / 2), 0
    end
    return
  end
  local cmd = bit.rshift(v, 24)
  if cmd == 0xA0 or cmd == 0x02 or cmd == 0xC0 then st.hdr, st.kind = 2, cmd end
end
local function on_write(port)
  return function()
    local pc = tonumber(PCSX.getRegisters().pc) % 4294967296
    local ok, v = pcall(reg_value, pc)
    note(port, ok and v % 4294967296 or -1)
    if cur() == S2 and S2.total > MAX_WORDS2 then runaway(MAX_WORDS2 .. ' GPU words written without reaching done') end
  end
end
local keep = {
  PCSX.addBreakpoint(GP0, 'Write', 4, 'ch16 gp0', on_write(0)),
  PCSX.addBreakpoint(GP1, 'Write', 4, 'ch16 gp1', on_write(1)),
  PCSX.addBreakpoint(GP1, 'Read', 4, 'ch16 stat', function()
    reads = reads + 1
    if d and d.phase == 2 and reads > MAX_READS2 then runaway(MAX_READS2 .. ' GPUSTAT reads without reaching done: a wait that never ends') end
  end),
}

-- ---- VRAM -------------------------------------------------------------------------------------------
local N = 1024 * 512
local before = ffi.new('uint16_t[?]', N)
local function vram_ptr() return ffi.cast('const uint16_t*', PCSX.GPU.getVRAM().data) end
local function snapshot() ffi.copy(before, vram_ptr(), N * 2) end

-- ---- the calls ---------------------------------------------------------------------------------------
local calls = {}
local function add_init()
  calls[#calls + 1] = { fn = 'gpu_init', limit = 2000,
    prepare = function() for i = 0, 12, 4 do verify.write_u32(SP + i, 0xBAD00000 + i) end end }
end
local function upload(x, y, w, h, buf_off)
  local n = w * h
  local nwords = math.floor((n + 1) / 2)
  local ptr = BUF + 4 * (buf_off or rnd(64))
  local c = { fn = 'vram_upload', a0 = ptr, a1 = x, a2 = y, a3 = w, x = x, y = y, w = w, h = h, ptr = ptr,
              limit = 60 * nwords + 3000 }
  c.prepare = function(cc)
    S1 = new_state()
    snapshot()
    cc.r0 = reads
    cc.px = {}
    for i = 0, nwords * 2 - 1 do cc.px[i] = rnd(65536) end
    for i = 0, nwords - 1 do verify.write_u32(ptr + 4 * i, cc.px[2 * i] + 65536 * cc.px[2 * i + 1]) end
    if n % 2 == 1 then verify.write_u32(ptr + 4 * (nwords - 1), cc.px[n - 1] + 65536 * rnd(65536)) end   -- junk pad half
    for i = 0, 15 do verify.write_u32(ptr + 4 * (nwords + i), 0xDEAD0000 + i) end                       -- junk after
    for i = 0, 12, 4 do verify.write_u32(SP + i, 0xBAD00000 + i) end
    verify.write_u32(SP + 16, h)
    for i = 20, 44, 4 do verify.write_u32(SP + i, 0xBADBAD00 + i) end
  end
  c.check = function(cc, rec)
    local p = vram_ptr()
    local bad, first, outside, ofirst = 0, nil, 0, nil
    for yy = 0, 511 do
      local row = yy * 1024
      local iny = yy >= y and yy < y + h
      for xx = 0, 1023 do
        local a = p[row + xx]
        if iny and xx >= x and xx < x + w then
          local want = cc.px[(yy - y) * w + (xx - x)]
          if a ~= want then
            bad = bad + 1
            if not first then first = { xx, yy, a, want } end
          end
        elseif a ~= before[row + xx] then
          outside = outside + 1
          if not ofirst then ofirst = { xx, yy, before[row + xx], a } end
        end
      end
    end
    rec.bad, rec.first_bad, rec.outside, rec.first_outside = bad, first, outside, ofirst
    rec.log, rec.pending = S1.log, S1.data
    rec.ndata = S1.ndata
    rec.px, rec.sent, rec.a0, rec.a1, rec.a2, rec.a3 = nil, nil, nil, nil, nil, nil
    rec.x, rec.y, rec.w, rec.h, rec.ptr, rec.r0 = x, y, w, h, ptr, cc.r0
    S1 = new_state()
  end
  calls[#calls + 1] = c
end

add_init()
for _, px in ipairs({ 320, 2, 640, 0, 16, 1022, 2 * rnd(256), 2 * rnd(256), 24 }) do
  calls[#calls + 1] = { fn = 'bpp24_halfwords', a0 = px, px = px, limit = 200,
    prepare = function() for i = 0, 12, 4 do verify.write_u32(SP + i, 0xBAD00000 + i) end end }
end
upload(0, 0, 2, 2)                            -- tiny, even
upload(10, 20, 1, 1)                          -- one pixel: one word, the upper half is padding
upload(100, 50, 7, 5)                         -- odd width, odd pixel count (35)
upload(300, 100, 33, 3)                       -- 99 pixels
upload(1023, 511, 1, 1)                       -- the very last pixel of VRAM
upload(1024 - 64, 512 - 8, 64, 8)             -- flush with the right and bottom edges
upload(1024 - 5, 3, 5, 9)                     -- right edge, odd count (45)
upload(0, 0, 1023, 3)                         -- wide, odd count (3069)
upload(320, 240, 480, 2)                      -- a 24-bpp-sized line pair
upload(5, 5, 16, 16)
upload(900, 500, 124, 12)                     -- bottom edge
for _ = 1, 4 do
  local w, h = 1 + rnd(40), 1 + rnd(12)
  upload(rnd(1024 - w + 1), rnd(512 - h + 1), w, h)
end

d = DC.new{ calls = calls, routines = { 'gpu_init', 'vram_upload', 'bpp24_halfwords' }, limit = 3000,
  on_exception = function(info) verify.record('seed', DC.seed); verify.record('calls', d.records)
    verify.record('exception', info); verify.finish('crash') end }
verify.record('seed', DC.seed)          -- tables are recorded by reference: final contents are written at the end
verify.record('calls', d.records)
verify.record('entries', d.entries)
verify.record('gpu', S2.log)
verify.on_exec('done', function() verify.record('gpu_total', S2.total); verify.record('gpu_pending', S2.data) end)
_G.ch16_keep = { keep, d.keep }
