"""Chapter 6 checks: Bug Hunt.

Three buggy programs (bug1, bug2, bug3), a findings.txt, and a Lua trace script.

* The fixed programs are run with inputs patched into the built EXEs (random each time), so a
  program that hard-codes its answers fails.
* findings.txt is compared with the addresses of the faulty instructions in verify/pristine/,
  an untouched copy of the starter programs with a marker label (`__bugN`) in front of each
  faulty instruction. The addresses come from assembling that copy, so they do not move when the
  reader edits the starter.  (If you change the starter sources, change pristine/ the same way:
  the two must stay identical apart from the `__bugN:` lines. `--solution` runs, i.e. CI, enforce
  this with a tooling error whenever git says starter/ is unmodified.)
* trace.lua is run by PCSX-Redux against the pristine bug3 with random inputs. The probe records
  the true value of $at at every execution of the faulty instruction; the script's output must match.
"""
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import harness as H
from harness import *

config(
    title="Emulation and Debugging: Bug Hunt",
    exe="bug1.ps-exe", sym="bug1.sym", main="bug1.s",
    break_at="done", reads={"results": 16}, max_frames=300,
)

HERE = Path(__file__).resolve().parent
M = 0xFFFFFFFF
KEY = 0x5EC0DE77
NEEDED = {
    1: ("main", "done", "inputs", "samples", "guard", "results"),
    2: ("main", "done", "words", "results"),
    3: ("main", "done", "inputs", "samples", "results"),
}
FINDING_HINT = {
    1: "Run the starter and put a read breakpoint on `guard`. Then ask why the loop went round once too often: "
       "the address is that of the branch that decides it.",
    2: "Open the disassembly around the loop's `bne`. Count the words the `li` after it became, and "
       "remember what a delay slot does with them. The address is that of the first word of that `li`.",
    3: "Step through the loop watching `at` in the Registers window. The address is that of the first "
       "instruction of the pseudo-instruction that overwrites it.",
}


# ---------------------------------------------------------------- helpers
def prog(ctx, n):
    """(BuildInfo, Symbols) of the reader's bugN, built by their Makefile."""
    bdir = ctx.build.build_dir
    exe, sym = bdir / f"bug{n}.ps-exe", bdir / f"bug{n}.sym"
    if not exe.exists() or not sym.exists():
        raise CheckFailure(expected=f"build/bug{n}.ps-exe and build/bug{n}.sym",
                           actual="not produced by `make`",
                           hint="Keep all three programs in the project and keep the Makefile.")
    return H.BuildInfo(True, "", bdir, exe, sym), Symbols.load(str(sym))


def run_prog(ctx, n, name, **over):
    cache = ctx.__dict__.setdefault("_ch06_runs", {})
    if name not in cache:
        b, s = prog(ctx, n)
        cache[name] = H.run_emulator(H.CFG.replace(exe=b.exe.name), b, s, ctx.work, name,
                                     timeout=ctx.timeout, probe=HERE / "probe.lua", **over)
    return cache[name]


def pristine(ctx, n):
    """(BuildInfo, Symbols) of the verifier's own untouched, labelled copy of bugN."""
    d = ctx.work / "pristine"
    if not d.exists():
        shutil.copytree(HERE / "pristine", d)
        shutil.copytree(H.ROOT / "common", d / "common")
    sym = d / f"bug{n}.sym"
    if not sym.exists():
        rc, log = H._run(["armips", f"bug{n}.s", "-sym", sym.name], d, H.tool_env())
        if rc != 0:
            raise HarnessError(f"pristine bug{n} failed to build:\n{log}")
    return H.BuildInfo(True, "", d, d / f"bug{n}.ps-exe", sym), Symbols.load(str(sym))


def check_pristine_sync(ctx):
    """Authoring guard, --solution only: pristine/bugN.s minus its marker == starter/bugN.s.
    Skipped when git says the tracked starter has local edits (a reader working in place)."""
    if not ctx.solution:
        return
    starter = HERE.parent / "starter"
    try:
        rc = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "."], cwd=starter,
                            capture_output=True, timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        return
    if rc != 0:
        return
    bad = []
    for n in (1, 2, 3):
        pr = (HERE / "pristine" / f"bug{n}.s").read_text().splitlines()
        if sum(l.strip() == f"__bug{n}:" for l in pr) != 1:
            bad.append(f"pristine/bug{n}.s must contain exactly one `__bug{n}:` line")
        if [l for l in pr if l.strip() != f"__bug{n}:"] != (starter / f"bug{n}.s").read_text().splitlines():
            bad.append(f"pristine/bug{n}.s differs from starter/bug{n}.s")
    if bad:
        raise HarnessError("verify/pristine/ is out of sync with starter/:\n  " + "\n  ".join(bad))


def fault_addr(ctx, n):
    return pristine(ctx, n)[1][f"__bug{n}"]


def blob(*vals):
    return b"".join(u32(v & M) for v in vals)


def rnd():
    return random.Random()   # fresh entropy every verify run


def parse_findings(ctx):
    p = ctx.project / "findings.txt"
    if not p.exists():
        raise CheckFailure(expected="a file findings.txt in your project", actual="missing")
    found = {}
    for line in p.read_text(errors="replace").splitlines():
        m = re.match(r"\s*bug\s*([123])\s*[:=]\s*(?:0x)?([0-9a-fA-F]{8})\b", line, re.I)
        if m:
            found[int(m.group(1))] = int(m.group(2), 16)
    return found


# ---------------------------------------------------------------- static
@static_check("the three programs, findings.txt and trace.lua exist",
              hint="Keep bug1.s, bug2.s, bug3.s, findings.txt and trace.lua in the project directory.")
def _(ctx):
    check_pristine_sync(ctx)
    missing = [f for f in ("bug1.s", "bug2.s", "bug3.s", "findings.txt", "trace.lua")
               if not (ctx.project / f).exists()]
    expect_true(not missing, "all five files present", f"missing: {', '.join(missing)}")


@static_check("each program keeps the labels the verifier patches and reads",
              hint="Do not rename or delete main, done, inputs, samples, guard, words or results.")
def _(ctx):
    for n, names in NEEDED.items():
        _, syms = prog(ctx, n)
        miss = [x for x in names if x not in syms]
        expect_true(not miss, f"bug{n} defines {', '.join(names)}", f"bug{n} lacks: {', '.join(miss)}")


# ---------------------------------------------------------------- behaviour
@check("bug1 adds exactly `count` words (three inputs)",
       hint="results[0] is the sum of the first `count` samples and results[1] is `count`. If results[1] is one "
            "too many, the loop runs once more than it should: look at what the counter is when it stops.")
def _(ctx):
    r = rnd()
    cases = [(8, [r.randrange(1, 1 << 20) for _ in range(8)]),
             (r.randrange(2, 8), [r.randrange(1, 1 << 20) for _ in range(8)]),
             (1, [r.randrange(1, 1 << 20) for _ in range(8)])]
    for i, (count, smp) in enumerate(cases):
        res = run_prog(ctx, 1, f"b1_{i}", patches={"inputs": count, "samples": blob(*smp)})
        expect_eq(res.u32("results", 1), count, f"bug1 words read (count={count})",
                  hint="The loop reads more or fewer words than `count`.")
        expect_eq(res.u32("results", 0), sum(smp[:count]) & M, f"bug1 sum (count={count})",
                  hint="The sum is wrong. Did the loop read a word it should not (the `guard`)?")


@check("bug2 sums (word XOR key) for every word (three inputs)",
       hint="Every pass must start with the full key 0x5EC0DE77. Look at what the `li` in the delay slot really "
            "executes on a taken branch.")
def _(ctx):
    r = rnd()
    sets = [[r.randrange(1 << 32) for _ in range(6)],
            [0, M, r.randrange(1 << 32), 1, r.randrange(1 << 32), 0x80000000],
            [r.randrange(1 << 16) for _ in range(6)]]
    for i, w in enumerate(sets):
        res = run_prog(ctx, 2, f"b2_{i}", patches={"words": blob(*w)})
        want = sum(x ^ KEY for x in w) & M
        expect_eq(res.u32("results", 0), want, f"bug2 checksum, words {[hex(x) for x in w]}",
                  hint="Only the first word was combined with the whole key.")


@check("bug3 reports the right total and word count (three inputs)",
       hint="A total that stays in $at is overwritten by the next pseudo-instruction that needs $at as a scratch.")
def _(ctx):
    r = rnd()
    smp = lambda: [r.randrange(1, 40) for _ in range(8)]

    def model(limit, count, s):
        total = 0
        for i in range(count):
            total += s[i]
            if total >= limit:
                return limit, i + 1
        return total, count

    cases = []
    s = smp(); cases.append((sum(s) + r.randrange(1, 50), 8, s))                  # never saturates
    s = smp(); c = r.randrange(3, 8); cases.append((sum(s[:c - 1]) + 1 + r.randrange(0, s[c - 1]), 8, s))  # saturates at word c
    s = smp(); cases.append((r.randrange(1, s[0] + 1), r.randrange(1, 9), s))     # saturates at word 1
    for i, (limit, count, s) in enumerate(cases):
        res = run_prog(ctx, 3, f"b3_{i}", patches={"inputs": blob(limit, count), "samples": blob(*s)})
        total, added = model(limit, count, s)
        what = f"limit={limit} count={count} samples={s}"
        expect_eq(res.u32("results", 0), total, f"bug3 total ({what})")
        expect_eq(res.u32("results", 1), added, f"bug3 words added ({what})")


# ---------------------------------------------------------------- findings
def _finding_check(n):
    @check(f"findings.txt: bug{n} names the faulty instruction", hint=FINDING_HINT[n])
    def _(ctx):
        found = parse_findings(ctx)
        if n not in found:
            raise CheckFailure(expected=f"a line like `bug{n}: 0x80010000` in findings.txt (8 hex digits)",
                               actual=f"no valid bug{n} line",
                               hint="Fill in all three lines of findings.txt.")
        want = fault_addr(ctx, n)
        expect_eq(found[n], want, f"bug{n} address in findings.txt", hint=FINDING_HINT[n], fmt="hex")
    return _


for _n in (1, 2, 3):
    _finding_check(_n)


# ---------------------------------------------------------------- Lua trace
def _trace_run(ctx):
    cache = ctx.__dict__.setdefault("_ch06_runs", {})
    if "trace" not in cache:
        r = rnd()
        s = [r.randrange(3, 30) for _ in range(8)]
        count = r.randrange(5, 9)
        limit = sum(s[:count]) + r.randrange(20, 60)        # never saturates: one hit per word
        b, syms = pristine(ctx, 3)
        os.environ["CH06_TRACE"] = str(ctx.project / "trace.lua")
        try:
            cache["trace"] = H.run_emulator(H.CFG.replace(exe=b.exe.name), b, syms, ctx.work, "trace",
                                            timeout=ctx.timeout, probe=HERE / "probe.lua",
                                            patches={"inputs": blob(limit, count), "samples": blob(*s)})
        finally:
            del os.environ["CH06_TRACE"]
    return cache["trace"]


@check("trace.lua loads and runs under PCSX-Redux without a Lua error",
       hint="Test it yourself: pcsx-redux -exe build/bug3.ps-exe -run -fastboot -interpreter -debugger -dofile trace.lua  (see the chapter, section 7).")
def _(ctx):
    res = _trace_run(ctx)
    res.require_finished()
    err = res.record("trace_error")
    expect_true(err is None, "trace.lua runs to the end", f"Lua error: {err}")
    errs = [l for l in res.log.splitlines() if re.search(r"lua.*(error|stack traceback)|attempt to", l, re.I)]
    expect_true(not errs, "no Lua errors in the emulator log", errs[0] if errs else "")


@check("trace.lua prints `at=0x........` for every hit of the faulty bug3 instruction",
       hint="One line per hit, value taken from the live register, exactly like `at=0x0000000a`. "
            "The address is the one in findings.txt for bug3. Remember: keep the breakpoint object in a global.")
def _(ctx):
    res = _trace_run(ctx)
    res.require_finished()
    truth = res.record("truth") or []
    expect_true(len(truth) >= 5, "the verifier saw at least 5 hits", f"{len(truth)} hits (harness problem?)")
    got = [int(m.group(1), 16) for l in res.log.splitlines()
           if (m := re.search(r"\bat\s*=\s*0x([0-9a-fA-F]{1,8})\b", l))]
    expect_eq(" ".join(f"{v:#x}" for v in got), " ".join(f"{v:#x}" for v in truth),
              "values of $at at each hit (this run's random inputs)",
              hint="The script must print $at (not a constant) once per execution of the instruction.")
