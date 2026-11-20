"""Chapter checks template -- copy to <chapter>/verify/checks.py.
API reference: tools/verify-lib/README.md
"""
from harness import *          # config, check, static_check, expect_*, Image helpers, u32, ...

config(
    title="Registers, Loads, Stores",      # shown in the report header
    # build="armips" is the default for projects without Makefile/CMakeLists.
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done",                        # label the starter declares (infinite loop)
    reads={"results": 64},                  # snapshot 64 bytes at label `results` when `done` is hit
    max_frames=600,
)


@static_check("program defines main, done and results",
              hint="Keep the labels the starter declares.")
def _(ctx):
    ctx.require_symbols("main", "done", "results")


@check("results[0] == 1 + 2", hint="Did you store the sum with sw?")
def _(ctx):
    expect_eq(ctx.result.u32("results", 0), 3, "results[0]")


@check("works for other inputs too (hard-coded answers fail)",
       hint="Your code must read `input` from memory rather than assume its value.")
def _(ctx):
    r = ctx.run(patches={"input": 10})      # patches the built .ps-exe, runs a 2nd emulator session
    expect_eq(r.u32("results", 0), 55, "results[0] for input=10")
