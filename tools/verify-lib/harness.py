#!/usr/bin/env python3
"""harness.py -- the PS1 book's chapter verification harness (standard library only).

Entry point used by every chapter's verify.sh:

    harness.py --chapter-dir <chNN-slug dir> [--solution] [-v] [--keep]
               [--timeout SECONDS] [path-to-project]

Pipeline (Summary section 4):
    build -> static checks -> run PCSX-Redux headless with a probe -> JSON results
          -> named checks (PASS/FAIL, expected/actual/hint) -> final line
    CHAPTER NN: PASSED (k/k checks)   or   CHAPTER NN: FAILED (j/k checks)
Exit codes: 0 all checks passed; 1 build failure or failed check(s) (includes the
emulator hard timeout); 2 harness/tooling problem (tool missing, bad checks.py).

Chapter authors write <chapter>/verify/checks.py using the API exported here:
see tools/verify-lib/README.md.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent
ROOT = LIB_DIR.parent.parent
TOOLCHAIN = Path(os.environ.get("PS1BOOK_TOOLCHAIN", ROOT / ".toolchain"))
DEFAULT_TIMEOUT = 20.0

# Make the book toolchain visible to this process (objdump/nm used by symbols.py).
os.environ["PATH"] = f"{TOOLCHAIN / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from failure import CheckFailure, HarnessError  # noqa: E402,F401
from symbols import Symbols, PsxExe, mnemonic  # noqa: E402
from image import (Image, Vram, colors_close, expect_pixel, expect_region, expect_solid,  # noqa: E402,F401
                   expect_pixel_differs, expect_similar, ahash, dhash, hamming, bgr555,
                   rgb_from_bgr555)


# =============================================================================
# Failure type + expectation helpers
# =============================================================================
def _fmt(v, fmt="auto"):
    if isinstance(v, int) and not isinstance(v, bool):
        if fmt == "hex":
            return f"0x{v & 0xFFFFFFFF:08X}" if v >= -0x80000000 else hex(v)
        if fmt == "dec":
            return str(v)
        return f"{v} (0x{v & 0xFFFFFFFF:08X})" if abs(v) > 9 else str(v)
    if isinstance(v, (bytes, bytearray)):
        return "bytes[" + v[:32].hex(" ") + (" ..." if len(v) > 32 else "") + "]"
    return repr(v) if isinstance(v, str) else str(v)


def u32(v):
    """Little-endian 4-byte encoding (for patches)."""
    return (v & 0xFFFFFFFF).to_bytes(4, "little")


def u16(v):
    return (v & 0xFFFF).to_bytes(2, "little")


def words(*vals):
    return b"".join(u32(v) for v in vals)


def expect_eq(actual, expected, what="", hint="", fmt="auto"):
    if actual != expected:
        raise CheckFailure(expected=(f"{what}: " if what else "") + _fmt(expected, fmt),
                           actual=_fmt(actual, fmt), hint=hint)


def expect_true(cond, expected="condition holds", actual="condition is false", hint=""):
    if not cond:
        raise CheckFailure(expected=expected, actual=actual, hint=hint)


def expect_near(actual, expected, tol, what="", hint=""):
    if abs(actual - expected) > tol:
        raise CheckFailure(expected=(f"{what}: " if what else "") + f"{expected} +/- {tol}",
                           actual=str(actual), hint=hint)


def expect_bytes(actual, expected, what="bytes", hint=""):
    if bytes(actual) != bytes(expected):
        i = next((k for k in range(min(len(actual), len(expected))) if actual[k] != expected[k]),
                 min(len(actual), len(expected)))
        raise CheckFailure(
            expected=f"{what}: {_fmt(bytes(expected))}",
            actual=f"{_fmt(bytes(actual))}  (first difference at byte offset {i}; "
                   f"lengths {len(actual)} vs {len(expected)})", hint=hint)


def expect_in(needle, haystack, what="", hint=""):
    if needle not in haystack:
        raise CheckFailure(expected=f"{what or 'value'} contains {needle!r}", actual="not found", hint=hint)


EXC_NAMES = {4: "address error on load/fetch", 5: "address error on store", 6: "bus error on fetch",
             7: "bus error on data", 8: "syscall", 9: "break", 10: "reserved instruction", 11: "coprocessor unusable",
             12: "arithmetic overflow"}


def exception_text(exc):
    """'' or '; CPU exception ...' for an exception record from directcall.lua ({code, epc, badvaddr})."""
    if not exc:
        return ""
    code = exc.get("code", -1)
    return (f"; CPU exception {code} ({EXC_NAMES.get(code, 'unknown')}) at pc 0x{exc.get('epc', 0):08X}, "
            f"bad address 0x{exc.get('badvaddr', 0):08X}")


# =============================================================================
# Configuration + registries
# =============================================================================
class Config:
    """Per-chapter settings; create with `config(...)` in checks.py."""
    DEFAULTS = dict(
        build=None,          # None=auto | "armips" | "make" | "cmake" | [argv...]
        main="main.s",       # armips entry file (build="armips")
        armips_args=(),      # extra armips flags, e.g. ("-erroronwarning",)
        no_warnings=False,   # fail the build if the tool output mentions "warning"
        exe="main.ps-exe",   # built executable (relative to the build dir; see README)
        sym="main.sym",      # symbol file ("" -> read symbols from the ELF given in `elf`)
        elf=None,            # ELF for nm-based symbols (C chapters)
        iso=None,            # .cue to boot from disc instead of side-loading `exe`
        break_at="done",     # symbol/address to stop at; None = run to max_frames
        max_frames=600,      # emulated video frames before giving up (60/s NTSC)
        settle_frames=2,     # keep running this many frames after the break (GPU settle)
        reads={},            # {name: size | (symbol_or_addr, size)} snapshotted at break
        shots=(),            # "end" | frame number | (name, frame)
        vram=False,          # dump VRAM at the end
        inputs=(),           # [(frame, "START", hold_frames), ...]
        patches={},          # {symbol_or_addr: bytes | int(u32)} applied to the exe pre-run
        probe=None,          # path to probe.lua (default: verify/probe.lua if it exists)
        ram_8mb=False,       # emulate 8 MB RAM
        extra_redux_args=(), # raw extra pcsx-redux flags
        timeout=None,        # per-emulator-run hard timeout in seconds; raises (never lowers) the default 20 s / --timeout
        title="",
    )

    def __init__(self, **kw):
        unknown = set(kw) - set(self.DEFAULTS)
        if unknown:
            raise TypeError(f"config(): unknown option(s) {sorted(unknown)}; valid: {sorted(self.DEFAULTS)}")
        for k, v in {**self.DEFAULTS, **kw}.items():
            setattr(self, k, v)

    def replace(self, **kw):
        d = {k: getattr(self, k) for k in self.DEFAULTS}
        d.update(kw)
        return Config(**d)


CFG = Config()
CHECKS = []


def config(**kw):
    """Set the chapter configuration (call once, at the top of checks.py)."""
    global CFG
    CFG = Config(**kw)
    return CFG


class Check:
    """A named assertion. `fn(ctx)` returns None to pass or raises CheckFailure."""

    def __init__(self, name, fn, hint="", kind="run"):
        self.name, self.fn, self.hint, self.kind = name, fn, hint, kind

    def __repr__(self):
        return f"Check({self.name!r}, kind={self.kind})"


def check(name, hint=""):
    """Decorator: register a check that may use the emulator run (ctx.result)."""
    def deco(fn):
        CHECKS.append(Check(name, fn, hint, "run"))
        return fn
    return deco


def static_check(name, hint=""):
    """Decorator: register a check that only inspects build artifacts/sources."""
    def deco(fn):
        CHECKS.append(Check(name, fn, hint, "static"))
        return fn
    return deco


# =============================================================================
# Toolchain environment
# =============================================================================
def tool_env():
    env = dict(os.environ)
    env["PS1BOOK_ROOT"] = str(ROOT)
    env["PS1BOOK_TOOLCHAIN"] = str(TOOLCHAIN)
    env["PATH"] = f"{TOOLCHAIN / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env.setdefault("PSN00BSDK_LIBS", str(TOOLCHAIN / "opt/psn00bsdk/lib/libpsn00b"))
    return env


def need_tool(name):
    p = shutil.which(name, path=tool_env()["PATH"])
    if not p:
        raise HarnessError(f"'{name}' not found. Run tools/setup.sh (then tools/doctor.sh).")
    return p


# =============================================================================
# Build
# =============================================================================
class BuildInfo:
    def __init__(self, ok, log, build_dir=None, exe=None, sym_path=None):
        self.ok, self.log, self.build_dir, self.exe, self.sym_path = ok, log, build_dir, exe, sym_path


def _run(cmd, cwd, env, timeout=300):
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise HarnessError(f"build tool not found: {cmd[0]} (run tools/setup.sh)")
    except subprocess.TimeoutExpired:
        return 124, f"build timed out after {timeout}s\n"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


_COPY_IGNORE = shutil.ignore_patterns("build", ".git", "__pycache__", "*.ps-exe", "*.exe", "*.elf",
                                      "*.sym", "*.o", "*.cue", "*.bin.out")


def build_project(project, cfg, work):
    env = tool_env()
    kind = cfg.build
    if kind is None:
        if (project / "Makefile").exists():
            kind = "make"
        elif (project / "CMakeLists.txt").exists():
            kind = "cmake"
        else:
            kind = "armips"
    log = ""
    if kind == "armips":
        need_tool("armips")
        stage = work / "stage"
        shutil.copytree(project, stage, ignore=_COPY_IGNORE, symlinks=True)
        common = ROOT / "common"
        if common.exists() and not (stage / "common").exists():
            shutil.copytree(common, stage / "common")
        if not (stage / cfg.main).exists():
            return BuildInfo(False, f"entry file '{cfg.main}' not found in {project}")
        cmd = ["armips", cfg.main, "-sym", Path(cfg.sym or "main.sym").name, *cfg.armips_args]
        rc, log = _run(cmd, stage, env)
        build_dir = stage
    elif kind == "make":
        need_tool("make")
        rc, log = _run(["make"], project, env)
        build_dir = project
        # templates/Makefile.armips writes its outputs to build/.
        if cfg.exe and not (project / cfg.exe).exists() and (project / "build" / cfg.exe).exists():
            build_dir = project / "build"
    elif kind == "cmake":
        need_tool("cmake")
        bdir = work / "cmake-build"
        sdk = env["PSN00BSDK_LIBS"] + "/cmake/sdk.cmake"
        rc, log = _run(["cmake", "-S", str(project), "-B", str(bdir), "-G", "Ninja", "-Wno-dev",
                        f"-DCMAKE_TOOLCHAIN_FILE={sdk}", "-DCMAKE_BUILD_TYPE=Release"], project, env)
        if rc == 0:
            rc, log2 = _run(["cmake", "--build", str(bdir)], project, env)
            log += log2
        build_dir = bdir
    elif isinstance(kind, (list, tuple)):
        rc, log = _run(list(kind), project, env)
        build_dir = project
    else:
        raise HarnessError(f"config(build=...) must be None, 'armips', 'make', 'cmake' or an argv list; got {kind!r}")
    if rc != 0:
        return BuildInfo(False, log, build_dir)
    if cfg.no_warnings and re.search(r"\bwarning\b", log, re.I):
        return BuildInfo(False, "build produced warnings (this chapter requires none):\n" + log, build_dir)
    exe = (build_dir / cfg.exe) if cfg.exe else None
    if cfg.iso:
        exe = None
    if exe is not None and not exe.exists():
        return BuildInfo(False, log + f"\nbuild succeeded but expected output '{cfg.exe}' was not produced "
                                f"in {build_dir}", build_dir)
    if cfg.iso and not (build_dir / cfg.iso).exists():
        return BuildInfo(False, log + f"\nexpected disc image '{cfg.iso}' was not produced", build_dir)
    sym_path = None
    if cfg.sym and (build_dir / cfg.sym).exists():
        sym_path = build_dir / cfg.sym
    elif cfg.elf and (build_dir / cfg.elf).exists():
        sym_path = build_dir / cfg.elf
    return BuildInfo(True, log, build_dir, exe, sym_path)


# =============================================================================
# Emulator run
# =============================================================================
def _lua_literal(v):
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(v, dict):
        return "{" + ",".join(f"[{_lua_literal(k)}]={_lua_literal(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(_lua_literal(x) for x in v) + "}"
    raise TypeError(f"cannot encode {type(v)} for Lua")


class RunResult:
    """What came back from one emulator run (`ctx.result` / `ctx.run(...)`)."""

    def __init__(self, outdir, cfg, symbols, data=None, timed_out=False, log="", exit_code=None,
                 launch_error=""):
        self.outdir, self.cfg, self.symbols = Path(outdir), cfg, symbols
        self.data = data or {}
        # Lua encodes empty tables as [] -- normalise the dict-valued fields.
        for k in ("mem", "shots", "records", "regs"):
            if k in self.data and isinstance(self.data[k], list):
                self.data[k] = {}
        self.timed_out, self.log, self.exit_code, self.launch_error = timed_out, log, exit_code, launch_error

    # ---- state ----
    @property
    def finished(self):
        return bool(self.data)

    @property
    def break_hit(self):
        return bool(self.data.get("break_hit"))

    @property
    def frames(self):
        return self.data.get("frames", 0)

    @property
    def cycles(self):
        return self.data.get("cycles", 0)

    @property
    def regs_at_break(self):
        return self.data.get("regs", {})

    @property
    def records(self):
        return self.data.get("records", {})

    def reg(self, name):
        """Register value when the break symbol was hit (e.g. r.reg('v0'), r.reg('pc'))."""
        self.require_finished()
        return self.regs_at_break[name]

    def record(self, key, default=None):
        """A value stored by probe.lua via verify.record(key, value)."""
        self.require_finished()
        return self.records.get(key, default)

    def require_finished(self):
        """Fail the calling check with a good message if the run produced nothing usable."""
        if self.launch_error:
            raise HarnessError(self.launch_error)
        if self.timed_out and not self.finished:
            raise CheckFailure(
                expected="program reaches its end point and PCSX-Redux exits",
                actual=f"emulator did not finish within the {getattr(self, 'timeout', DEFAULT_TIMEOUT):g}s hard timeout",
                hint="Infinite loop before the `done` label? A branch with a missing delay slot? "
                     "Run with -v to see the emulator log.")
        if not self.finished:
            raise CheckFailure(expected="emulator produced results.json",
                               actual="no results (emulator crashed or probe failed)",
                               hint="Run with -v and read the emulator log.")
        miss = self.data.get("missing_symbols") or []
        if miss:
            raise CheckFailure(expected="symbols defined: " + ", ".join(sorted(set(miss))),
                               actual="not found in your program",
                               hint="Keep the labels the starter declares; the probe finds your code through them.")
        errs = self.data.get("errors") or []
        if errs:
            raise HarnessError("probe/harness Lua errors:\n" + "\n".join(errs))

    def require_break(self):
        self.require_finished()
        if self.cfg.break_at and not self.break_hit:
            raise CheckFailure(
                expected=f"program reaches `{self.cfg.break_at}`",
                actual=f"never reached it in {self.frames} frames (status: {self.data.get('status')})"
                       + exception_text(self.records.get("exception")),
                hint=f"Does your program fall into an infinite loop, crash, or jump somewhere else "
                     f"before the `{self.cfg.break_at}:` label?")

    # ---- memory snapshots (cfg.reads) ----
    def mem(self, name):
        self.require_break()
        info = self.data.get("mem", {}).get(name)
        if not info:
            raise HarnessError(f"no memory snapshot named {name!r}; add it to config(reads={{...}})")
        return (self.outdir / info["file"]).read_bytes()

    def u8(self, name, index=0):
        return self.mem(name)[index]

    def u16(self, name, index=0):
        return int.from_bytes(self.mem(name)[2 * index:2 * index + 2], "little")

    def u32(self, name, index=0):
        return int.from_bytes(self.mem(name)[4 * index:4 * index + 4], "little")

    def s32(self, name, index=0):
        v = self.u32(name, index)
        return v - (1 << 32) if v & 0x80000000 else v

    def words(self, name, count=None, signed=False):
        b = self.mem(name)
        n = (len(b) // 4) if count is None else count
        out = [int.from_bytes(b[4 * i:4 * i + 4], "little", signed=signed) for i in range(n)]
        return out

    # ---- images ----
    def screenshot(self, name="end"):
        self.require_finished()
        info = self.data.get("shots", {}).get(name)
        if not info:
            raise HarnessError(f"no screenshot named {name!r}; add it to config(shots=[...])")
        return Image.load_ppm(self.outdir / info["file"])

    def screenshot_info(self, name="end"):
        self.require_finished()
        return self.data.get("shots", {}).get(name, {})

    def vram(self):
        self.require_finished()
        f = self.outdir / "vram.bin"
        if not f.exists():
            raise HarnessError("no VRAM dump; use config(vram=True)")
        return Vram.from_file(f)


def _normalize_reads(reads, symbols):
    out = []
    for name, spec in (reads or {}).items():
        if isinstance(spec, int):
            ref, size = name, spec
        else:
            ref, size = spec
        out.append((name, ref, size))
    return out


def run_emulator(cfg, build, symbols, work, name="default", timeout=DEFAULT_TIMEOUT, **over):
    """Run one emulator session. `over` may override any Config field (patches=, inputs=, ...)."""
    c = cfg.replace(**over) if over else cfg
    outdir = work / f"run-{name}"
    outdir.mkdir(parents=True, exist_ok=True)
    redux = need_tool("pcsx-redux")

    # --- program image (with patches applied to a copy) ---
    exe_path = None
    if build.exe is not None:
        exe_path = build.exe
        if c.patches:
            exe = PsxExe.load(build.exe)
            data = exe.data
            for ref, blob in c.patches.items():
                try:
                    addr = symbols.resolve(ref)
                except KeyError as e:
                    return _missing_symbol(outdir, c, symbols, ref)
                if isinstance(blob, int):
                    blob = u32(blob)
                data = PsxExe(data).patched(addr, bytes(blob))
            exe_path = outdir / "patched.ps-exe"
            exe_path.write_bytes(data)

    # --- reads / probe / job file ---
    reads = []
    for rname, ref, size in _normalize_reads(c.reads, symbols):
        try:
            addr = symbols.resolve(ref)
        except KeyError:
            return _missing_symbol(outdir, c, symbols, ref)
        reads.append({"name": rname, "addr": addr, "size": size})
    shots = []
    for s in c.shots:
        if s == "end":
            shots.append({"name": "end", "at_end": True})
        elif isinstance(s, int):
            shots.append({"name": f"f{s}", "frame": s})
        else:
            shots.append({"name": s[0], "frame": s[1]})
    probe = c.probe
    try:
        break_addr = symbols.resolve(c.break_at) if c.break_at else None
    except KeyError:
        return _missing_symbol(outdir, c, symbols, c.break_at)
    job = {
        "out": str(outdir),
        "max_frames": c.max_frames,
        "settle_frames": c.settle_frames,
        "break_at": break_addr,
        "reads": reads,
        "shots": shots,
        "vram": bool(c.vram),
        "inputs": [{"frame": i[0], "button": i[1], "hold": (i[2] if len(i) > 2 else 6)} for i in c.inputs],
        "probe": str(probe) if probe else None,
        "symbols": symbols.table,
    }
    job_file = outdir / "job.lua"
    job_file.write_text("return " + _lua_literal(job) + "\n")

    cmd = [redux, "-cli", "-testmode", "-stdout", "-lua_stdout", "-interpreter", "-debugger",
           "-1mbvram", "-fastboot", "-run", "-noupdate",
           "-memcard1", str(outdir / "mc1.mcd"), "-memcard2", str(outdir / "mc2.mcd")]
    if os.environ.get("PS1BOOK_BIOS"):
        cmd += ["-bios", os.environ["PS1BOOK_BIOS"]]
    if c.ram_8mb:
        cmd.append("-8mb")
    if c.iso:
        cmd += ["-iso", str(build.build_dir / c.iso)]
    else:
        cmd += ["-exe", str(exe_path)]
    cmd += list(c.extra_redux_args) + ["-dofile", str(LIB_DIR / "redux.lua")]

    env = tool_env()
    env["PS1BOOK_JOB"] = str(job_file)
    env.setdefault("HOME", str(work))
    t0 = time.time()
    timed_out = False
    log_path = outdir / "emulator.log"
    with open(log_path, "wb") as logf:
        p = subprocess.Popen(cmd, env=env, stdout=logf, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(p.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    p.wait(timeout=2)
                    break
                except subprocess.TimeoutExpired:
                    continue
    log = log_path.read_text(errors="replace")
    data = None
    rj = outdir / "results.json"
    if rj.exists():
        try:
            data = json.loads(rj.read_text())
        except json.JSONDecodeError as e:
            log += f"\n[harness] results.json unreadable: {e}"
    res = RunResult(outdir, c, symbols, data=data, timed_out=timed_out, log=log, exit_code=p.returncode)
    res.elapsed, res.timeout = time.time() - t0, timeout
    return res


def _missing_symbol(outdir, c, symbols, ref):
    """A symbol the run needs is absent from the reader's program: report it as a
    normal failed check (exit 1), not a tooling error."""
    name = re.split(r"\s*[+-]", str(ref), maxsplit=1)[0]
    r = RunResult(outdir, c, symbols, data={"missing_symbols": [name]},
                  log=f"[harness] symbol {name!r} not found; emulator not started")
    r.elapsed = 0.0
    return r


# =============================================================================
# Context passed to checks
# =============================================================================
class Context:
    def __init__(self, chapter_dir, project, cfg, work, solution, timeout):
        self.chapter_dir, self.project, self.cfg, self.work = chapter_dir, project, cfg, work
        self.solution, self.timeout = solution, max(timeout, cfg.timeout or 0)
        self.build = None
        self.symbols = Symbols()
        self._exe = None
        self._result = None
        self._runs = {}
        self._disasm = None

    # ---- build artifacts ----
    @property
    def exe(self):
        """Parsed PSX-EXE of the built program (header + code)."""
        if self._exe is None:
            if not self.build or not self.build.exe:
                raise HarnessError("no executable (config(exe=...) / iso-only chapter)")
            self._exe = PsxExe.load(self.build.exe)
        return self._exe

    @property
    def build_log(self):
        return self.build.log if self.build else ""

    def require_symbols(self, *names, hint=""):
        """Fail the check with a list of missing symbols."""
        miss = self.symbols.require(*names)
        if miss:
            raise CheckFailure(expected="symbols defined: " + ", ".join(names),
                               actual="missing: " + ", ".join(miss),
                               hint=hint or "Keep the labels the starter declares; the harness finds your code through them.")

    def source_files(self, pattern="**/*.s"):
        """Reader's source files (project dir), excluding build output."""
        return sorted(p for p in self.project.glob(pattern)
                      if p.is_file() and "build" not in p.relative_to(self.project).parts)

    def source_text(self, pattern="**/*.s", strip_comments=True):
        txt = "\n".join(p.read_text(errors="replace") for p in self.source_files(pattern))
        if strip_comments:
            txt = re.sub(r"(;|//).*", "", txt)
        return txt

    def disassemble(self):
        """List[Insn] of the built text segment (cached)."""
        if self._disasm is None:
            self._disasm = self.exe.disassemble()
        return self._disasm

    def disassemble_range(self, start, end):
        """Instructions with start <= addr < end (symbol names or addresses)."""
        a, b = self.symbols.resolve(start), self.symbols.resolve(end)
        return [i for i in self.disassemble() if a <= i.addr < b]

    # ---- emulator runs ----
    @property
    def result(self):
        """The default run (executed once, before the run-type checks)."""
        if self._result is None:
            self._result = self._exec("default")
        return self._result

    def run(self, name=None, **overrides):
        """Extra emulator run with config overrides (e.g. patches={...}, inputs=[...]).
        Cached by arguments. Each run costs ~1-2 s of wall time."""
        key = repr(sorted(overrides.items(), key=lambda kv: kv[0]))
        if key not in self._runs:
            self._runs[key] = self._exec(name or f"x{len(self._runs)}", **overrides)
        return self._runs[key]

    def _exec(self, name, **overrides):
        if "probe" not in overrides and self.cfg.probe is None:
            pr = self.chapter_dir / "verify" / "probe.lua"
            if pr.exists():
                overrides["probe"] = pr
        return run_emulator(self.cfg, self.build, self.symbols, self.work, name,
                            timeout=self.timeout, **overrides)


# =============================================================================
# Main
# =============================================================================
def _load_checks(verify_dir):
    path = verify_dir / "checks.py"
    if not path.exists():
        raise HarnessError(f"{path} not found")
    spec = importlib.util.spec_from_file_location("chapter_checks", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(verify_dir))
    try:
        spec.loader.exec_module(mod)
    except Exception:
        raise HarnessError(f"error importing {path}:\n{traceback.format_exc()}")
    return mod


def _chapter_number(chapter_dir, override):
    if override:
        return int(override)
    m = re.match(r"ch(\d+)", chapter_dir.name)
    return int(m.group(1)) if m else 0


def _run_check(ck, ctx):
    try:
        ck.fn(ctx)
        return True, None
    except CheckFailure as f:
        return False, f
    except HarnessError:
        raise
    except Exception as e:
        tb = traceback.format_exc().strip().splitlines()
        return False, CheckFailure(expected="check runs without error",
                                   actual=f"check raised {type(e).__name__}: {e}",
                                   hint="this is probably a bug in checks.py or the harness; "
                                        "location: " + (tb[-3].strip() if len(tb) >= 3 else "?"))


def main(argv=None):
    global DEFAULT_TIMEOUT
    ap = argparse.ArgumentParser(description="PS1 book chapter verifier")
    ap.add_argument("project", nargs="?", help="reader project dir (default: <chapter>/starter)")
    ap.add_argument("--chapter-dir", required=True)
    ap.add_argument("--chapter", type=int, help="chapter number (default: from dir name chNN-...)")
    ap.add_argument("--solution", action="store_true", help="verify <chapter>/solution instead")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="emulator hard timeout (s)")
    ap.add_argument("-v", "--verbose", action="store_true", help="show build output and emulator log")
    ap.add_argument("--keep", action="store_true", help="keep the temp work dir and print its path")
    a = ap.parse_args(argv)

    chapter_dir = Path(a.chapter_dir).resolve()
    num = _chapter_number(chapter_dir, a.chapter)
    tag = f"CHAPTER {num:02d}"
    DEFAULT_TIMEOUT = a.timeout
    if a.project and a.solution:
        print("error: give either --solution or a project path, not both", file=sys.stderr)
        return 2
    project = (chapter_dir / "solution") if a.solution else Path(a.project or chapter_dir / "starter")
    project = project.resolve()
    work = Path(tempfile.mkdtemp(prefix=f"ps1book-ch{num:02d}-"))
    try:
        return _main(a, chapter_dir, project, work, tag)
    except HarnessError as e:
        print(f"\nHARNESS ERROR: {e}")
        print(f"{tag}: ERROR (tooling problem, not a failed check)")
        return 2
    finally:
        if a.keep or os.environ.get("PS1BOOK_KEEP"):
            print(f"[work dir kept: {work}]")
        else:
            shutil.rmtree(work, ignore_errors=True)


def _main(a, chapter_dir, project, work, tag):
    verify_dir = chapter_dir / "verify"
    CHECKS.clear()
    mod = _load_checks(verify_dir)
    cfg = CFG
    title = cfg.title or getattr(mod, "TITLE", "")
    print(f"== {tag}{': ' + title if title else ''}")
    print(f"   project: {project}{'  (reference solution)' if a.solution else ''}")
    if not project.is_dir():
        print(f"error: project directory {project} does not exist")
        print(f"{tag}: FAILED (no project)")
        return 1
    if not CHECKS:
        raise HarnessError("checks.py registered no checks (use @check / @static_check)")

    # 1. build
    print("-- build")
    build = build_project(project, cfg, work)
    if a.verbose or not build.ok:
        print(_indent(build.log.rstrip() or "(no output)"))
    if not build.ok:
        print("   BUILD FAILED. Fix the errors above and run verify again.")
        print(f"{tag}: FAILED (build error)")
        return 1
    print("   build ok")

    ctx = Context(chapter_dir, project, cfg, work, a.solution, a.timeout)
    ctx.build = build
    if build.sym_path:
        try:
            ctx.symbols = Symbols.load(str(build.sym_path))
        except Exception as e:
            raise HarnessError(f"cannot read symbols from {build.sym_path}: {e}")

    results = []   # (Check, ok, failure)

    def do(ck):
        ok, f = _run_check(ck, ctx)
        results.append((ck, ok, f))
        print(f"  {'PASS' if ok else 'FAIL'}  {ck.name}")
        if not ok:
            if f.message and not f.expected and not f.actual:
                print(f"        {f.message}")
            if f.expected is not None:
                print(f"        expected: {f.expected}")
            if f.actual is not None:
                print(f"        actual:   {f.actual}")
            hint = f.hint or ck.hint
            if hint:
                print(f"        hint:     {hint}")

    # 2. static checks
    statics = [c for c in CHECKS if c.kind == "static"]
    if statics:
        print("-- static checks")
        for ck in statics:
            do(ck)

    # 3. run
    runs = [c for c in CHECKS if c.kind == "run"]
    if runs:
        miss = [n for n in ([cfg.break_at] if isinstance(cfg.break_at, str) else []) if n not in ctx.symbols]
        print("-- run (PCSX-Redux headless)")
        if miss:
            print(f"   symbol(s) not found, cannot run to them: {', '.join(miss)}")
        else:
            res = ctx.result
            note = "timed out" if res.timed_out else f"{res.frames} frames"
            print(f"   emulator: {note}, {getattr(res, 'elapsed', 0):.1f}s wall")
            if a.verbose:
                print(_indent(res.log.rstrip()))
        print("-- checks")
        for ck in runs:
            if miss:
                f = CheckFailure(expected=f"label `{miss[0]}` exists in your program",
                                 actual="not found in the symbol table",
                                 hint="Keep the labels declared by the starter (`done:`, `results:`).")
                results.append((ck, False, f))
                print(f"  FAIL  {ck.name}\n        expected: {f.expected}\n        actual:   {f.actual}\n        hint:     {f.hint}")
            else:
                do(ck)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    ok_all = passed == total
    if not ok_all and not a.verbose and runs and ctx._result is not None and ctx._result.timed_out:
        print("   (emulator hit the hard timeout; re-run with -v for its log)")
    print(f"{tag}: {'PASSED' if ok_all else 'FAILED'} ({passed}/{total} checks)")
    return 0 if ok_all else 1


def _indent(s, n=6):
    pad = " " * n
    return "\n".join(pad + l for l in s.splitlines())


if __name__ == "__main__":
    # Re-import under the canonical name so `from harness import ...` in checks.py
    # shares one registry with this entry point.
    import harness as _h
    sys.exit(_h.main())
