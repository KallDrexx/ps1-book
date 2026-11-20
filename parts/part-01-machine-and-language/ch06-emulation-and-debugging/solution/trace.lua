-- Chapter 6: print $at every time the clobbering instruction of bug3 is about to run.
-- 0x80010038 is the address in findings.txt (the first word of the `bge` expansion).
local TARGET = 0x80010038

-- Keep the returned object in a global, or Lua's garbage collector removes the breakpoint.
traceBP = PCSX.addBreakpoint(TARGET, 'Exec', 4, 'trace $at', function()
    local gpr = PCSX.getRegisters().GPR.n
    print(string.format('at=0x%08x', tonumber(gpr.at)))
end)
