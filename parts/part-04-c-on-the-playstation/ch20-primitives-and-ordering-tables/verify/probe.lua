-- Chapter 20 probe (does not disturb the program). Records
--   ev[]   every GP1 05h (display start) write made inside display_swap(): {vsync frame, frame_no}
--   cl[]   every call of ClearOTagR: {frame_no, ot pointer, length}
--   dw[]   every call of DrawOTag: {vsync frame, frame_no, head pointer, guards_ok, nodes, terminated,
--          depths = the 16 scene depths at that moment, prims = flat list [node, len, code, r, g, b, entry, ...]}
--          (entry = address of the last len-0 node, i.e. the table entry, walked before the packet)
--          where the packets are found by WALKING the DMA linked list from the head, exactly as the GPU's DMA would.
-- A runaway (no VBlank wait) ends the run early.
local GP1 = 0x1F801814
local MAX_EV = 400
local FRAME_SZ, GUARD_OFF, GUARD_N = 2320, 2304, 16   -- OtFrame: ot[64] + prim[2048] + guard[16]
local ev, cl, dw = {}, {}, {}
local runaway = false
local swaps = 0

local function reg_value(pc)
  local w = verify.u32(pc % 0x200000 + 0x80000000)
  return tonumber(PCSX.getRegisters().GPR.r[bit.band(bit.rshift(w, 16), 31)]) % 4294967296
end

local function on_gp1()
  local pc = tonumber(PCSX.getRegisters().pc) % 4294967296
  local ok, v = pcall(reg_value, pc)
  if not ok or bit.rshift(v, 24) ~= 0x05 or swaps == 0 then return end
  ev[#ev + 1] = { verify.frame, verify.u32('frame_no') }
  verify.record('ev', ev)
  if #ev > MAX_EV and not runaway then
    runaway = true
    verify.record('runaway', MAX_EV .. ' display-start writes: no wait for VBlank?')
    verify.finish('runaway')
  end
end
ch20_keep = { PCSX.addBreakpoint(GP1, 'Write', 4, 'ch20 gp1', on_gp1) }
verify.on_exec('display_swap', function() swaps = swaps + 1 end)

local function guards_ok()
  local base = verify.resolve('ot_frames')
  for f = 0, 1 do
    for i = 0, GUARD_N - 1 do
      if verify.u8(base + f * FRAME_SZ + GUARD_OFF + i) ~= 0xA5 then return false end
    end
  end
  return true
end

-- (hooked only if the program links them, so a starter fails with a clear message)
if verify.sym.ClearOTagR then verify.on_exec('ClearOTagR', function(r)
  cl[#cl + 1] = { verify.u32('frame_no'), r.a0, r.a1 }
  verify.record('cl', cl)
end) end

if verify.sym.DrawOTag and verify.sym.ot_frames then verify.on_exec('DrawOTag', function(r)
  local node = r.a0
  local prims, nodes, terminated, entry = {}, 0, false, 0
  while nodes < 3000 do
    local w = verify.u32(node)
    local len, nxt = bit.rshift(w, 24), bit.band(w, 0xFFFFFF)
    nodes = nodes + 1
    if len > 0 then
      local c = verify.u32(node + 4)
      prims[#prims + 1] = node
      prims[#prims + 1] = len
      prims[#prims + 1] = bit.rshift(c, 24)
      prims[#prims + 1] = bit.band(c, 255)
      prims[#prims + 1] = bit.band(bit.rshift(c, 8), 255)
      prims[#prims + 1] = bit.band(bit.rshift(c, 16), 255)
      prims[#prims + 1] = entry
    else
      entry = node
    end
    if nxt == 0xFFFFFF then terminated = true break end
    node = 0x80000000 + nxt
  end
  local depths = {}
  for i = 0, 15 do depths[#depths + 1] = verify.s32('scene+' .. (16 * i + 12)) end
  dw[#dw + 1] = { verify.frame, verify.u32('frame_no'), r.a0, guards_ok(), nodes, terminated, depths, prims }
  verify.record('dw', dw)
end) end
