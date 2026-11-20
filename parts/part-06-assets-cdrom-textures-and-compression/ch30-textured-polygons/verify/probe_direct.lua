-- Chapter 30 probe, direct-call run. checks.py writes a small file that defines CASES and then loads this one.
-- The first time the program calls frame_done() with frame_no >= 3 (textures loaded, loop running), the probe saves the registers
-- and calls the reader's functions from here, one after the other, then restores the registers and ends the run:
--   CASES.parse { name, data = {bytes}, misalign = bool }   -> tim_parse(&info, data, #data)
--   CASES.tex   { name, info = {11 words} }                 -> tex_from_tim(&tex, &info)
-- Per parse call it records v0 and the TimInfo struct (11 words, pre-filled with 0xA5A5A5A5) and the data address; per tex call the
-- six halfwords of the Tex struct (pre-filled with 0xA5A5).
local R = PCSX.getRegisters()
local GPR = R.GPR.r
local IDX = { v0 = 2, a0 = 4, a1 = 5, a2 = 6, sp = 29, ra = 31 }
local TRAMP = 0x80090000
local PATH, OUTSZ, MODEL, DATA = 0x80180000, 0x80180100, 0x80180110, 0x80181000

local function regget(i) return tonumber(GPR[i]) % 4294967296 end
local function regset(i, v) GPR[i] = v % 4294967296 end

local queue, recs = {}, {}
local active = nil

local function put(addr, bytes) for i, b in ipairs(bytes) do verify.write_u8(addr + i - 1, b) end end

for _, c in ipairs(CASES.parse) do
  queue[#queue + 1] = {
    kind = 'parse', name = c.name, fn = 'tim_parse',
    setup = function()
      for i = 0, 10 do verify.write_u32(MODEL + 4 * i, 0xA5A5A5A5) end
      local at = c.misalign and DATA + 1 or DATA
      put(at, c.data)
      return MODEL, at, #c.data
    end,
    finish = function(rec)
      local w = {}
      for i = 0, 10 do w[#w + 1] = verify.u32(MODEL + 4 * i) end
      rec.info = w
      rec.data_addr = c.misalign and DATA + 1 or DATA
    end,
  }
end
for _, c in ipairs(CASES.tex) do
  queue[#queue + 1] = {
    kind = 'tex', name = c.name, fn = 'tex_from_tim',
    setup = function()
      for i = 0, 5 do verify.write_u16(OUTSZ + 2 * i, 0xA5A5) end
      for i = 0, 10 do verify.write_u32(MODEL + 4 * i, c.info[i + 1] % 4294967296) end
      return OUTSZ, MODEL, 0
    end,
    finish = function(rec)
      local w = {}
      for i = 0, 5 do w[#w + 1] = verify.u16(OUTSZ + 2 * i) end
      rec.tex = w
    end,
  }
end

local saved, saved_pc, started, idx, main_sp = nil, 0, false, 0, 0

local function restore()
  for i = 1, 31 do regset(i, saved[i]) end
  R.pc = saved_pc
end

local function next_call()
  idx = idx + 1
  local q = queue[idx]
  if not q then
    restore()
    verify.record('cases', recs)
    verify.finish('done')
    return
  end
  active = q
  q.frame0 = verify.frame
  local a0, a1, a2 = q.setup()
  regset(IDX.a0, a0); regset(IDX.a1, a1); regset(IDX.a2, a2)
  regset(IDX.ra, TRAMP)
  regset(IDX.sp, main_sp - 1024)
  R.pc = verify.resolve(q.fn)
end

verify.write_u32(TRAMP, 0x08000000 + math.floor((TRAMP % 0x10000000) / 4))   -- j TRAMP
verify.write_u32(TRAMP + 4, 0)

local tramp_bp = PCSX.addBreakpoint(TRAMP, 'Exec', 4, 'verify tramp', function()
  local q = active
  if not q then return end
  active = nil
  local rec = { kind = q.kind, name = q.name, v0 = regget(IDX.v0) }
  q.finish(rec)
  recs[#recs + 1] = rec
  next_call()
end)

local exc_bp = PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
  if not started then return end
  local cp0 = R.CP0.r
  local code = math.floor((tonumber(cp0[13]) or 0) / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = (tonumber(cp0[14]) or 0) % 4294967296, badvaddr = (tonumber(cp0[8]) or 0) % 4294967296,
                               fn = active and active.fn or '', name = active and active.name or '' })
  verify.record('cases', recs)
  verify.finish('exception')
  return false
end)
_G.ch30_keep = { tramp_bp, exc_bp }

verify.on_exec('frame_done', function()
  if started then return end
  if verify.s32('frame_no') < 3 then return end
  started = true
  saved = {}
  for i = 1, 31 do saved[i] = regget(i) end
  saved_pc = tonumber(R.pc) % 4294967296
  main_sp = saved[IDX.sp]
  next_call()
end)
