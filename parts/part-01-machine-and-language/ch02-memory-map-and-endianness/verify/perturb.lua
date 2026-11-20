-- Perturbation run: the first time the program reads a source word, swap in a
-- different value. If the copies in results follow the new value, they came from
-- real loads; if they still show the original constants, they were hard-coded.
local swaps = {
  { ref = "results",      want = 0x12345678, new = 0x8BADF00D },
  { ref = "results+12",   want = 0xDEADBEEF, new = 0x0C0FFEE5 },
  { ref = 0x1F800000,     want = 0x600DCAFE, new = 0x5CA77E12 },
}
local done_swaps = {}
for i, s in ipairs(swaps) do
  verify.on_access("Read", s.ref, 4, function(a, w, pc)
    if done_swaps[i] then return false end
    done_swaps[i] = true
    if verify.u32(s.ref) == s.want then
      verify.write_u32(s.ref, s.new)
      verify.record("swapped" .. i, true)
    end
    return false
  end)
end
