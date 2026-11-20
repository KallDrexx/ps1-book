-- Chapter 32 probe, direct-call run. checks.py writes a small file that defines CASES and then loads this one.
-- The first time the program calls frame_done() with frame_no >= 3 (the pack is loaded, the frame loop is running), the probe saves the
-- registers and calls the reader's functions from here, one after the other, then restores the registers and ends the run.
-- A case is { name, fn, args = {a0, a1, a2, a3}, writes = { {addr, "hex"}, ... }, reads = { {addr, nbytes}, ... } }.
-- Per call it records { name, v0, cycles, reads = { "hex", ... } } where cycles is the CPU cycle counter between the call and its return.
local R = PCSX.getRegisters()
local GPR = R.GPR.r
local MEM = PCSX.getMemPtr()
local IDX = { v0 = 2, a0 = 4, a1 = 5, a2 = 6, a3 = 7, sp = 29, ra = 31 }
local TRAMP = 0x80090000

local function regget(i) return tonumber(GPR[i]) % 4294967296 end
local function regset(i, v) GPR[i] = v % 4294967296 end

local function put(addr, hex)
  local base = addr % 0x20000000
  for i = 1, #hex / 2 do MEM[base + i - 1] = tonumber(hex:sub(2 * i - 1, 2 * i), 16) end
end

local function get(addr, n)
  local base, t = addr % 0x20000000, {}
  for i = 0, n - 1 do t[#t + 1] = string.format('%02x', MEM[base + i]) end
  return table.concat(t)
end

local recs = {}
local active = nil
local saved, saved_pc, started, idx, main_sp = nil, 0, false, 0, 0

local function restore()
  for i = 1, 31 do regset(i, saved[i]) end
  R.pc = saved_pc
end

local function next_call()
  idx = idx + 1
  local c = CASES[idx]
  if not c then
    restore()
    verify.record('cases', recs)
    verify.finish('done')
    return
  end
  for _, w in ipairs(c.writes or {}) do put(w[1], w[2]) end
  active = c
  c.t0 = verify.cycles()
  for k = 1, 4 do regset(IDX.a0 + k - 1, (c.args or {})[k] or 0) end
  regset(IDX.ra, TRAMP)
  regset(IDX.sp, main_sp - 2048)
  R.pc = verify.resolve(c.fn)
end

verify.write_u32(TRAMP, 0x08000000 + math.floor((TRAMP % 0x10000000) / 4))   -- j TRAMP
verify.write_u32(TRAMP + 4, 0)

local tramp_bp = PCSX.addBreakpoint(TRAMP, 'Exec', 4, 'verify tramp', function()
  local c = active
  if not c then return end
  active = nil
  local rec = { name = c.name, v0 = regget(IDX.v0), cycles = verify.cycles() - c.t0, reads = {} }
  for _, rd in ipairs(c.reads or {}) do rec.reads[#rec.reads + 1] = get(rd[1], rd[2]) end
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
_G.ch32_keep = { tramp_bp, exc_bp }

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
