-- Chapter 6 probe. Only active for the "trace" run (CH06_TRACE = path of the reader's Lua script):
--   * records the ground truth: $at at every execution of the buggy bug3 instruction (label __bug3
--     exists only in the verifier's pristine copy of the program);
--   * then loads the reader's script, exactly as `pcsx-redux -dofile trace.lua` would.
local trace = os.getenv("CH06_TRACE")
if trace then
  local hits = {}
  verify.record("truth", hits)
  verify.on_exec("__bug3", function(r) hits[#hits + 1] = r.at end)
  local ok, err = pcall(dofile, trace)
  if not ok then verify.record("trace_error", tostring(err)) end
end
