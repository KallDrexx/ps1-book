-- Chapter 29 probe, direct-call run. checks.py writes a small file that defines CASES and then loads this one.
-- The first time the program calls frame_done() with frame_no >= 3 (the model is loaded and the loop is running), the
-- probe saves the registers and calls the reader's functions from here, one after the other, then restores the registers
-- and ends the run:
--   CASES.cd    { name, path = {bytes}, null_size = bool }   -> cd_load_file(path, &size)   (size pointer NULL if null_size)
--   CASES.parse { name, data = {bytes}, misalign = bool }    -> model_parse(&m, data, #data)
-- Per cd call it records: v0, the size word, the first 32 bytes, the last 16 bytes before `size`, a hash of the `size`
-- bytes (h = (h * 31 + byte) mod 2^32), every malloc/calloc request made during the call (outside CdSearchFile), and how many times CdSearchFile
-- and CdRead were entered. Per parse call: v0, the Model struct (4 words) and whether a 0xA5A5A5A5 sentinel survived.
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

for _, c in ipairs(CASES.cd) do
  queue[#queue + 1] = {
    kind = 'cd', name = c.name, fn = 'cd_load_file',
    setup = function()
      local p = {}
      for i, b in ipairs(c.path) do p[i] = b end
      p[#p + 1] = 0
      put(PATH, p)
      verify.write_u32(OUTSZ, 0xDEADBEEF)
      return PATH, c.null_size and 0 or OUTSZ, 0
    end,
    finish = function(rec)
      rec.size_word = verify.u32(OUTSZ)
      local v0 = rec.v0
      if v0 ~= 0 and not c.null_size and rec.size_word > 0 and rec.size_word < 0x100000 then
        local n = rec.size_word
        local h = 0
        for i = 0, n - 1 do h = (h * 31 + verify.u8(v0 + i)) % 4294967296 end
        rec.hash = h
        local head, tail = {}, {}
        for i = 0, math.min(31, n - 1) do head[#head + 1] = verify.u8(v0 + i) end
        for i = math.max(0, n - 16), n - 1 do tail[#tail + 1] = verify.u8(v0 + i) end
        rec.head, rec.tail = head, tail
      elseif v0 ~= 0 and c.null_size then
        local head = {}
        for i = 0, 31 do head[#head + 1] = verify.u8(v0 + i) end
        rec.head = head
      end
    end,
  }
end
for _, c in ipairs(CASES.parse) do
  queue[#queue + 1] = {
    kind = 'parse', name = c.name, fn = 'model_parse',
    setup = function()
      for i = 0, 3 do verify.write_u32(MODEL + 4 * i, 0xA5A5A5A5) end
      local at = c.misalign and DATA + 1 or DATA
      put(at, c.data)
      return MODEL, at, #c.data
    end,
    finish = function(rec)
      rec.model = { verify.u32(MODEL), verify.u32(MODEL + 4), verify.u32(MODEL + 8), verify.u32(MODEL + 12) }
      rec.data_addr = c.misalign and DATA + 1 or DATA
    end,
  }
end

local saved, saved_pc, started, idx, main_sp = nil, 0, false, 0, 0
local mallocs, search, reads = {}, 0, 0

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
  mallocs, search, reads = {}, 0, 0
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
  local rec = { kind = q.kind, name = q.name, v0 = regget(IDX.v0), mallocs = mallocs, search = search, reads = reads,
                frames = verify.frame - q.frame0 }
  q.finish(rec)
  recs[#recs + 1] = rec
  next_call()
end)

local function hook(name, fn)
  if verify.sym[name] then verify.on_exec(name, fn) end
end
-- CdSearchFile allocates its own path-table and directory caches (a directory is 2048 bytes): those requests are not
-- the reader's buffer, so mallocs made while CdSearchFile runs are not counted.
local in_search = false
hook('malloc', function(r) if active and not in_search then mallocs[#mallocs + 1] = r.a0 end end)
hook('calloc', function(r) if active and not in_search then mallocs[#mallocs + 1] = (r.a0 * r.a1) % 4294967296 end end)
hook('CdSearchFile', function(r)
  if not active then return end
  search = search + 1
  if not in_search then
    in_search = true
    verify.on_exec(r.ra % 4294967296, function() in_search = false; return false end)
  end
end)
hook('CdRead', function() if active then reads = reads + 1 end end)
hook('CdReadRetry', function() if active then reads = reads + 1 end end)

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
_G.ch29_keep = { tramp_bp, exc_bp }

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
