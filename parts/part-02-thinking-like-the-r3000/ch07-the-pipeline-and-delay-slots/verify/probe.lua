-- Chapter 7 probe. In every run it records:
--   n1, n2  instructions executed inside [fact_v1, fact_v1_end) and [fact_v2, fact_v2_end)
--   mul2    multiply instructions (mult/multu) executed inside version 2
local function span(a, b)
  return verify.resolve(a), verify.resolve(b)
end

local a1, b1 = span("fact_v1", "fact_v1_end")
local a2, b2 = span("fact_v2", "fact_v2_end")
local c1 = (b1 > a1) and verify.count_instructions("fact_v1", "fact_v1_end") or { n = 0 }
local c2 = (b2 > a2) and verify.count_instructions("fact_v2", "fact_v2_end") or { n = 0 }
local mul = { n = 0 }

-- The program is in RAM by the time `main` first executes: find the multiplies then.
verify.on_exec("main", function()
  for a = a2, b2 - 4, 4 do
    local w = verify.u32(a)
    local f = bit.band(w, 0x3F)
    if bit.rshift(w, 26) == 0 and (f == 0x18 or f == 0x19) then
      verify.on_exec(a, function() mul.n = mul.n + 1 end)
    end
  end
  return false
end)

verify.on_exec("done", function()
  verify.record("n1", c1.n)
  verify.record("n2", c2.n)
  verify.record("mul2", mul.n)
end)
