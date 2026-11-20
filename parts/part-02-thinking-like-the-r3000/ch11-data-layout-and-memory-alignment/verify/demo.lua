-- Chapter 11 demo probe: runs the book's example/ program (never the reader's code) and records the
-- first CPU exception: Cop0 Cause (exception code), BadVAddr, EPC and the faulting instruction word,
-- plus the example's `results` words (so we can see that the safe lwr/lwl read worked).
local R = PCSX.getRegisters()
local done = false
_G.ch11_demo_bp = PCSX.addBreakpoint(0x80000080, 'Exec', 4, 'ch11 demo exception', function()
  if done then return false end
  local cp0 = R.CP0.r
  local cause, epc, bad = tonumber(cp0[13]) or 0, tonumber(cp0[14]) or 0, tonumber(cp0[8]) or 0
  local code = math.floor(cause / 4) % 32
  if code == 0 then return end                         -- an interrupt
  done = true
  verify.record('code', code)
  verify.record('badvaddr', bad % 4294967296)
  verify.record('epc', epc % 4294967296)
  verify.record('insn', verify.u32(epc % 4294967296))
  verify.record('r0', verify.u32('results'))
  verify.record('r1', verify.u32('results+4'))
  verify.finish('exception')
  return false
end)
