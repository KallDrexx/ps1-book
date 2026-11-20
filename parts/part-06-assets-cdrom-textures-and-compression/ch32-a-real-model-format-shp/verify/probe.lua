-- Chapter 32 probe (main and alt runs). Observes; boots from the disc image.
-- The program is frozen and posed by the probe: at the end of every frame the probe writes spin_step = 0, render_mode and the three
-- angles of the NEXT scenario, so the following frame is drawn with them. At the end of that frame it records one scenario:
--   { index, mode, ax, ay, az, frame_no, prims_submitted, sxy = {...}, sz = {...}, mtx = {8 words}, prims = { slot, len, w1 .. wlen, ... } }
-- where prims is the flat list of the packets found by walking the ordering table DrawOTag was given (slot, tag length in words, then the
-- words after the tag). A screenshot "s<index>" is taken at the same moment.
-- At frame_no == 3 the probe records "info": load_status, tpk_status, shp_status, cam_z, proj_h, shp_info words and the store.
-- PARAMS (optional global set by a wrapper): { scenarios = { {mode=, ax=, ay=, az=}, ... } }.
local FIRST = 4                                        -- the first scenario is set at the end of frame FIRST - 1
local FRAME_SZ = 2320                                  -- OtFrame: ot[64] + prim[2048] + guard[16]
local ANGLES = { { 192, 3584, 0 }, { 160, 1024, 0 }, { 3840, 2560, 128 } }
local scenarios = (PARAMS and PARAMS.scenarios) or nil
if not scenarios then
  scenarios = {}
  for mode = 0, 1 do
    for _, a in ipairs(ANGLES) do scenarios[#scenarios + 1] = { mode = mode, ax = a[1], ay = a[2], az = a[3] } end
  end
end

local function s16(a)
  local v = verify.u16(a)
  return v >= 32768 and v - 65536 or v
end

local out = {}
verify.record('scenarios', out)

PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'verify exception', function()
  local cp0 = PCSX.getRegisters().CP0.r
  local code = math.floor((tonumber(cp0[13]) or 0) / 4) % 32
  if code == 0 or code == 8 then return end
  verify.record('exception', { code = code, epc = (tonumber(cp0[14]) or 0) % 4294967296, badvaddr = (tonumber(cp0[8]) or 0) % 4294967296 })
  verify.finish('exception')
  return false
end)

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
        prims[#prims + 1] = math.floor(((entry - base) % FRAME_SZ) / 4)
        prims[#prims + 1] = len
        for k = 1, len do prims[#prims + 1] = verify.u32(node + 4 * k) end
      else
        entry = node
      end
      if nxt == 0xFFFFFF then break end
      node = 0x80000000 + nxt
    end
    pending = prims
  end)
end

local function arm(sc)
  verify.write_u32('spin_step', 0)
  verify.write_u32('render_mode', sc.mode)
  verify.write_u32('angle_x', sc.ax)
  verify.write_u32('angle_y', sc.ay)
  verify.write_u32('angle_z', sc.az)
end

verify.on_exec('frame_done', function()
  local n = verify.s32('frame_no')
  if n == 3 then
    local si = verify.resolve('shp_info')
    local words = {}
    for i = 0, 15 do words[#words + 1] = verify.u32(si + 4 * i) end
    local st = verify.resolve('store')
    local count = verify.s32(st)
    local tex = { count }
    for i = 0, math.min(math.max(count, 0), 255) * 6 - 1 do tex[#tex + 1] = verify.u16(st + 12 + 2 * i) end
    verify.record('info', { load_status = verify.s32('load_status'), tpk_status = verify.s32('tpk_status'), shp_status = verify.s32('shp_status'),
                            cam_z = verify.s32('cam_z'), proj_h = verify.s32('proj_h'), shp_info = words, store = tex })
  end
  if n < FIRST - 1 then return end
  local k = n - (FIRST - 1)                              -- scenario k was posed at the end of frame FIRST-2+k and is drawn in this frame
  if k >= 1 and scenarios[k] then
    local sc = scenarios[k]
    local nv = verify.s32('shp_info') ~= nil and verify.s32(verify.resolve('shp_info') + 32) or 0
    local sxy, sz = {}, {}
    local bx, bz = verify.resolve('screen_xy'), verify.resolve('screen_z')
    for i = 0, math.min(nv, 256) - 1 do sxy[#sxy + 1] = verify.u32(bx + 4 * i); sz[#sz + 1] = verify.u32(bz + 4 * i) end
    local mt, mb = {}, verify.resolve('mtx')
    for i = 0, 7 do mt[#mt + 1] = verify.u32(mb + 4 * i) end
    out[#out + 1] = { index = k, mode = sc.mode, ax = sc.ax, ay = sc.ay, az = sc.az, frame_no = n, load_status = verify.s32('load_status'),
                      prims_submitted = verify.s32('prims_submitted'), sxy = sxy, sz = sz, mtx = mt, prims = pending,
                      angle_y_after = verify.s32('angle_y') }
    verify.screenshot('s' .. k)
  end
  pending = {}
  if scenarios[k + 1] then
    arm(scenarios[k + 1])
  elseif k >= #scenarios then
    verify.collect('done')
  end
end)
