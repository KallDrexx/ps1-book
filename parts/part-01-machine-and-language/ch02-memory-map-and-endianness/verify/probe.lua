local W, R = {}, {}
verify.on_access("Write", "results", 64, function(a, w, pc)
  W[#W + 1] = { a, w }
end)
verify.on_access("Read", "results", 16, function(a, w, pc)
  R[#R + 1] = { a, w }
end)
verify.on_access("Write", 0x1F800000, 4, function(a, w, pc) W[#W + 1] = { a, w } end)
verify.on_access("Read", 0x1F800000, 4, function(a, w, pc) R[#R + 1] = { a, w } end)
verify.on_exec("done", function()
  verify.record("writes", W)
  verify.record("reads", R)
  verify.record("results", verify.sym.results)
end)
