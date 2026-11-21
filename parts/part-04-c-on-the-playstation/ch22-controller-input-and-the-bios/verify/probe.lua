-- Chapter 22 probe. The buttons themselves are pressed by the harness (`inputs=`: PCSX-Redux pad overrides);
-- this file only observes. It records
--   st[]    once per vsync: {frame, x, y, color, input_update calls so far}   (read from cursor_state)
--   init    {n InitPAD calls, a0, a1, a2, a3 of the first call}, startpad = StartPAD calls
--   q[]     once per frame inside [Q0, Q1]: the results of calling the reader's input_held / input_pressed /
--           input_released DIRECTLY (twice each, for the masks below), from the entry of display_clear:
--           {frame, r[1..30]}  with r laid out as fn (held, pressed, released) x mask x repeat.
-- A direct call saves all registers, sets $a0 = mask, $ra = a trampoline, jumps to the function, reads $v0, and
-- finally restores the registers and lets display_clear run as if nothing happened.
local Q0, Q1 = 60, 140
local MASKS = { 0x4000, 0x0010, 0x4010, 0x0000, 0x8000 }     -- CROSS, UP, UP|CROSS, none, SQUARE
local FNS = { 'input_held', 'input_pressed', 'input_released' }
local TRAMP = 0x80090000

local st, q = {}, {}
local n_update, n_init, n_start = 0, 0, 0
local init_args = nil
verify.record('st', st)
verify.record('q', q)

if verify.sym.input_update then verify.on_exec('input_update', function() n_update = n_update + 1 end) end
if verify.sym.StartPAD then verify.on_exec('StartPAD', function()
  n_start = n_start + 1
  verify.record('startpad', n_start)
end) end
if verify.sym.InitPAD then verify.on_exec('InitPAD', function(r)
  n_init = n_init + 1
  if not init_args then init_args = { r.a0, r.a1, r.a2, r.a3 } end
  verify.record('initpad', { n_init, init_args[1], init_args[2], init_args[3], init_args[4] })
end) end

verify.on_vsync(function(frame)
  if verify.sym.cursor_state then
    st[#st + 1] = { frame, verify.s32('cursor_state'), verify.s32('cursor_state+4'),
                    verify.s32('cursor_state+8'), n_update }
  end
end)

-- ---- direct calls of the three queries ---------------------------------------------------------------------
local R = PCSX.getRegisters()
local GPR = R.GPR.r
local function get(i) return tonumber(GPR[i]) % 4294967296 end
local function set(i, v) GPR[i] = v % 4294967296 end
local have = verify.sym.display_clear
for _, f in ipairs(FNS) do have = have and verify.sym[f] end

if have then
  local dc = verify.resolve('display_clear')
  local jobs, saved, saved_pc, idx, row, done_frame = {}, nil, 0, 0, nil, -1
  for _, f in ipairs(FNS) do
    for _, m in ipairs(MASKS) do
      for _ = 1, 2 do jobs[#jobs + 1] = { fn = verify.resolve(f), mask = m } end
    end
  end
  local function launch()
    idx = idx + 1
    if idx > #jobs then
      for i = 1, 31 do set(i, saved[i]) end
      R.pc = saved_pc
      saved = nil
      q[#q + 1] = row
      return
    end
    local j = jobs[idx]
    for i = 1, 31 do if i ~= 28 and i ~= 29 then set(i, 0) end end   -- keep $gp and $sp
    set(29, (saved[29] - 256) - ((saved[29] - 256) % 8))
    set(4, j.mask)
    set(31, TRAMP)
    R.pc = j.fn
  end
  verify.write_u32(TRAMP, 0)
  tramp_keep = PCSX.addBreakpoint(TRAMP, 'Exec', 4, 'ch22 tramp', function()
    if not saved then return end
    row[#row + 1] = get(2)
    launch()
  end)
  dc_keep = PCSX.addBreakpoint(dc, 'Exec', 4, 'ch22 queries', function()
    local f = verify.frame
    if f < Q0 or f > Q1 or saved or done_frame == f then return end
    done_frame = f
    saved = {}
    for i = 1, 31 do saved[i] = get(i) end
    saved_pc = dc
    idx, row = 0, { f }
    launch()
  end)
end
