-- redux.lua -- Lua side of the verification harness, loaded into PCSX-Redux with
--   pcsx-redux -cli -testmode ... -dofile redux.lua      (job file path in $PS1BOOK_JOB)
--
-- The harness (harness.py) writes a job file (a Lua table) describing what to do;
-- this script runs the program, snapshots state, writes results.json (+ binary
-- side files) into JOB.out and quits PCSX-Redux. Chapter probes (probe.lua) are
-- loaded afterwards and use the global `verify` table defined here.
--
-- LuaJIT (Lua 5.1 semantics): no `//` operator, no integer type, use `bit.*`.

local ffi = require('ffi')
local bit = require('bit')

local JOB_PATH = os.getenv('PS1BOOK_JOB')
assert(JOB_PATH, 'PS1BOOK_JOB not set')
local JOB = dofile(JOB_PATH)

verify = {}
local V = verify
V.job = JOB
V.libdir = (debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$')) or '.'  -- dir of this file (for dofile of shared Lua helpers)
V.frame = 0
V.sym = JOB.symbols or {}
V.records = {}
V.errors = {}
V.shots = {}
V.files = {}            -- name -> relative file name of memory snapshots
V.break_hit = false
V.break_frame = nil
V.regs_at_break = nil
V.finished = false

local keep = {}         -- strong refs: breakpoints/listeners are removed when GC'd
local frame_actions = {} -- frame -> list of functions
local every_frame = {}

-- ---------------------------------------------------------------- JSON writer
local function is_array(t)
  local n = 0
  for k in pairs(t) do
    if type(k) ~= 'number' then return false end
    n = n + 1
  end
  return n == #t
end

local escapes = { ['"'] = '\\"', ['\\'] = '\\\\', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
local function json(v, out)
  local t = type(v)
  if t == 'nil' then out[#out + 1] = 'null'
  elseif t == 'boolean' then out[#out + 1] = v and 'true' or 'false'
  elseif t == 'number' then
    if v ~= v or v == math.huge or v == -math.huge then out[#out + 1] = 'null'
    elseif v == math.floor(v) and math.abs(v) < 2^53 then out[#out + 1] = string.format('%d', v)
    else out[#out + 1] = string.format('%.9g', v) end
  elseif t == 'string' then
    out[#out + 1] = '"' .. v:gsub('[%c"\\]', function(c)
      return escapes[c] or string.format('\\u%04x', c:byte()) end) .. '"'
  elseif t == 'cdata' then json(tonumber(v), out)
  elseif t == 'table' then
    if is_array(v) then
      out[#out + 1] = '['
      for i = 1, #v do if i > 1 then out[#out + 1] = ',' end json(v[i], out) end
      out[#out + 1] = ']'
    else
      out[#out + 1] = '{'
      local first = true
      local keys = {}
      for k in pairs(v) do keys[#keys + 1] = k end
      table.sort(keys, function(x, y) return tostring(x) < tostring(y) end)
      for _, k in ipairs(keys) do
        if not first then out[#out + 1] = ',' end
        first = false
        json(tostring(k), out); out[#out + 1] = ':'
        json(v[k], out)
      end
      out[#out + 1] = '}'
    end
  else json(tostring(v), out) end
end
function V.to_json(v) local o = {} json(v, o) return table.concat(o) end

-- ---------------------------------------------------------------- helpers
local function out_path(name) return JOB.out .. '/' .. name end

V.missing = {}
local function fail(msg)
  local sym = tostring(msg):match('ps1book:unknown%-symbol:([%w_.$]+)')
  if sym then
    V.missing[#V.missing + 1] = sym
    print('[verify] program does not define symbol: ' .. sym)
    return
  end
  V.errors[#V.errors + 1] = tostring(msg)
  print('[verify] ERROR: ' .. tostring(msg))
end

local function safe(fn, ...)
  local ok, err = xpcall(fn, debug.traceback, ...)
  if not ok then fail(err) end
  return ok, err
end

function V.resolve(ref)
  if type(ref) == 'number' then return ref end
  local name, off = ref:match('^([%w_.$]+)%s*([+-]%s*%w+)$')
  if not name then name = ref; off = nil end
  local a = V.sym[name]
  if not a then error('ps1book:unknown-symbol:' .. tostring(name), 0) end
  if off then a = a + tonumber((off:gsub('%s', ''))) end
  return a
end

-- Pointer into emulated RAM / scratchpad for a (KUSEG/KSEG0/KSEG1) address.
local function ptr(addr)
  local a = bit.band(addr, 0x1FFFFFFF)
  if a < 0x800000 then return PCSX.getMemPtr() + a end
  if a >= 0x1F800000 and a < 0x1F800400 then return PCSX.getScratchPtr() + (a - 0x1F800000) end
  error(string.format('address 0x%08X is not RAM or scratchpad', addr))
end
V.ptr = ptr

function V.u8(addr)  return ptr(V.resolve(addr))[0] end
function V.u16(addr) return ffi.cast('uint16_t*', ptr(V.resolve(addr)))[0] end
function V.u32(addr) return tonumber(ffi.cast('uint32_t*', ptr(V.resolve(addr)))[0]) end
function V.s32(addr) return tonumber(ffi.cast('int32_t*', ptr(V.resolve(addr)))[0]) end
function V.write_u32(addr, v) ffi.cast('uint32_t*', ptr(V.resolve(addr)))[0] = v end
function V.write_u16(addr, v) ffi.cast('uint16_t*', ptr(V.resolve(addr)))[0] = v end
function V.write_u8(addr, v) ptr(V.resolve(addr))[0] = v end
function V.read_bytes(addr, n) return ffi.string(ptr(V.resolve(addr)), n) end

local GPR_NAMES = { 'zero','at','v0','v1','a0','a1','a2','a3','t0','t1','t2','t3','t4','t5','t6','t7',
                    's0','s1','s2','s3','s4','s5','s6','s7','t8','t9','k0','k1','gp','sp','fp','ra','lo','hi' }
function V.regs()
  local r = PCSX.getRegisters()
  local t = { pc = tonumber(r.pc) }
  for i = 0, 33 do t[GPR_NAMES[i + 1]] = tonumber(r.GPR.r[i]) end
  return t
end

function V.cycles() return tonumber(PCSX.getCPUCycles()) end
function V.record(key, value) V.records[key] = value end

-- Run fn(frame) every vsync (emulated video frame).
function V.on_vsync(fn) every_frame[#every_frame + 1] = fn end
-- Run fn() when the vsync counter reaches `frame` (1-based: first vsync is frame 1).
function V.at_frame(frame, fn)
  frame_actions[frame] = frame_actions[frame] or {}
  table.insert(frame_actions[frame], fn)
end

-- Exec breakpoint on a symbol/address. fn(regs_table) ; return false to remove.
function V.on_exec(ref, fn, width)
  local addr = V.resolve(ref)
  local bp = PCSX.addBreakpoint(addr, 'Exec', width or 4, 'verify exec', function()
    local ok, res = safe(fn, V.regs())
    if not ok or res == false then return false end
  end)
  keep[#keep + 1] = bp
  return bp
end

-- Count instructions executed with PC in [start, stop). Returns a table whose
-- field .n is the running count. (Interpreter + debugger are enabled by harness.)
function V.count_instructions(start_ref, stop_ref)
  local a, b = V.resolve(start_ref), V.resolve(stop_ref)
  local c = { n = 0 }
  keep[#keep + 1] = PCSX.addBreakpoint(a, 'Exec', b - a, 'verify count', function() c.n = c.n + 1 end)
  return c
end

-- Memory read/write breakpoints: fn(address, width, pc).
function V.on_access(kind, ref, width, fn)
  local addr = V.resolve(ref)
  local bp = PCSX.addBreakpoint(addr, kind, width or 4, 'verify ' .. kind, function(a, w)
    local ok, res = safe(fn, a, w, tonumber(PCSX.getRegisters().pc))
    if not ok or res == false then return false end
  end)
  keep[#keep + 1] = bp
  return bp
end

-- ---------------------------------------------------------------- pad
local pad = PCSX.SIO0.slots[1].pads[1]
local BUTTON = PCSX.CONSTS.PAD.BUTTON
V.BUTTON = BUTTON
function V.button_down(name) pad.setOverride(assert(BUTTON[name], 'unknown button ' .. name)) end
function V.button_up(name) pad.clearOverride(assert(BUTTON[name], 'unknown button ' .. name)) end
-- Hold `name` (e.g. 'START', 'CROSS', 'UP') from `frame` for `hold` frames.
function V.press(frame, name, hold)
  hold = hold or 6
  V.at_frame(frame, function() V.button_down(name) end)
  V.at_frame(frame + hold, function() V.button_up(name) end)
end

-- ---------------------------------------------------------------- screenshots / VRAM
function V.screenshot(name)
  local ss = PCSX.GPU.takeScreenShot()
  local w, h = ss.width, ss.height
  local bpp24 = tonumber(ss.bpp) ~= 0
  local buf = ffi.new('uint8_t[?]', w * h * 3)
  if not bpp24 then
    local p = ffi.cast('const uint16_t*', ss.data.data)
    for i = 0, w * h - 1 do
      local c = p[i]
      local r, g, b = bit.band(c, 31), bit.band(bit.rshift(c, 5), 31), bit.band(bit.rshift(c, 10), 31)
      buf[i * 3]     = bit.bor(bit.lshift(r, 3), bit.rshift(r, 2))
      buf[i * 3 + 1] = bit.bor(bit.lshift(g, 3), bit.rshift(g, 2))
      buf[i * 3 + 2] = bit.bor(bit.lshift(b, 3), bit.rshift(b, 2))
    end
  else
    ffi.copy(buf, ss.data.data, w * h * 3)
  end
  local fname = 'shot_' .. name .. '.ppm'
  local f = assert(io.open(out_path(fname), 'wb'))
  f:write(string.format('P6\n%d %d\n255\n', w, h))
  f:write(ffi.string(buf, w * h * 3))
  f:close()
  V.shots[name] = { file = fname, width = w, height = h, bpp = bpp24 and 24 or 16, frame = V.frame }
end

function V.dump_vram(name)
  name = name or 'vram'
  local v = PCSX.GPU.getVRAM()
  local f = assert(io.open(out_path(name .. '.bin'), 'wb'))
  f:write(ffi.string(v.data, v.size))
  f:close()
  V.records['_vram_' .. name] = { file = name .. '.bin', size = tonumber(v.size) }
end

-- Snapshot a named memory range to <out>/mem_<name>.bin (overwrites).
function V.snapshot(name, addr, size)
  local f = assert(io.open(out_path('mem_' .. name .. '.bin'), 'wb'))
  f:write(ffi.string(ptr(V.resolve(addr)), size))
  f:close()
  V.files[name] = { file = 'mem_' .. name .. '.bin', addr = V.resolve(addr), size = size, frame = V.frame }
end

local function snapshot_reads()
  for _, r in ipairs(JOB.reads or {}) do
    safe(function() V.snapshot(r.name, r.addr, r.size) end)
  end
end

-- ---------------------------------------------------------------- finishing
function V.finish(status, exit_code)
  if V.finished then return end
  V.finished = true
  local doc = {
    status = status,
    frames = V.frame,
    cycles = V.cycles(),
    break_hit = V.break_hit,
    break_frame = V.break_frame,
    regs = V.regs_at_break or V.regs(),
    mem = V.files,
    shots = V.shots,
    records = V.records,
    errors = V.errors,
    missing_symbols = V.missing,
  }
  local f = assert(io.open(out_path('results.json'), 'wb'))
  f:write(V.to_json(doc))
  f:close()
  print('[verify] finished: ' .. status .. ' at frame ' .. V.frame)
  PCSX.pauseEmulator()
  PCSX.quit(exit_code or ((#V.errors > 0) and 2 or 0))
end

-- Stop-and-collect (what happens `settle_frames` after the break symbol is hit,
-- or at the frame limit). Takes the requested screenshots and the VRAM dump.
local function collect(status)
  if not V.break_hit then snapshot_reads() end
  for _, s in ipairs(JOB.shots or {}) do
    if s.at_end then safe(V.screenshot, s.name) end
  end
  if JOB.vram then safe(V.dump_vram) end
  V.finish(status)
end
V.collect = collect

-- ---------------------------------------------------------------- default behaviour
local function on_break(regs)
  V.break_hit = true
  V.break_frame = V.frame
  V.regs_at_break = regs
  snapshot_reads()
  V.records.cycles_at_break = V.cycles()
  local settle = JOB.settle_frames or 0
  if settle <= 0 then collect('break') else
    V.at_frame(V.frame + settle, function() collect('break') end)
  end
  return false -- one-shot
end

if JOB.break_at then
  V.on_exec(JOB.break_at, on_break)
end

for _, s in ipairs(JOB.shots or {}) do
  if s.frame then V.at_frame(s.frame, function() V.screenshot(s.name) end) end
end
for _, i in ipairs(JOB.inputs or {}) do
  V.press(i.frame, i.button, i.hold)
end

vsync_listener = PCSX.Events.createEventListener('GPU::Vsync', function()
  V.frame = V.frame + 1
  local acts = frame_actions[V.frame]
  if acts then for _, a in ipairs(acts) do safe(a) end end
  for _, fn in ipairs(every_frame) do safe(fn, V.frame) end
  if not V.finished and V.frame >= (JOB.max_frames or 1200) then
    collect('frame_limit')
  end
end)

-- Chapter probe (optional): sees `verify`, may add breakpoints/records/finish early.
if JOB.probe then
  local chunk, err = loadfile(JOB.probe)
  if not chunk then fail('probe load error: ' .. tostring(err)) else safe(chunk, JOB) end
end
