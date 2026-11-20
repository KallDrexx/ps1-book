"""Chapter 1 checks: doctor.sh passes, the EXE is valid, and the screen colour
equals the colour recorded in color.txt (and is not the starter's default)."""
import re
import subprocess
from pathlib import Path

from harness import *

DEFAULT_RGB = (0x20, 0x40, 0x80)     # the colour the starter ships with
MIN_CHANGE = 24                      # some channel must move by more than quantisation + tolerance
ROOT = Path(__file__).resolve().parents[4]

config(
    title="The PlayStation and Your Workbench",
    main="main.s", exe="main.ps-exe", sym="main.sym",
    break_at="done", shots=["end"], max_frames=300,
)


def read_color(ctx):
    path = Path(ctx.project) / "color.txt"
    if not path.is_file():
        raise CheckFailure(expected="a file color.txt next to main.s",
                           actual="missing", message="color.txt not found", hint="Create color.txt containing the colour as RRGGBB hex, e.g. FF8000.")
    text = path.read_text().strip()
    m = re.fullmatch(r"#?([0-9A-Fa-f]{6})", text)
    if not m:
        raise CheckFailure(expected="six hex digits, RRGGBB",
                           actual=repr(text[:40]), message="color.txt is not a colour",
                           hint="Write only the colour, e.g. FF8000 (red, green, blue).")
    v = int(m.group(1), 16)
    return (v >> 16, (v >> 8) & 255, v & 255)


@static_check("toolchain passes tools/doctor.sh",
              hint="Run tools/setup.sh, then tools/doctor.sh, and fix every MISSING line.")
def _(ctx):
    p = subprocess.run([str(ROOT / "tools" / "doctor.sh")], capture_output=True, text=True)
    if p.returncode != 0:
        bad = [l.strip() for l in p.stdout.splitlines() if "MISSING" in l]
        raise CheckFailure(expected="exit code 0",
                           actual="; ".join(bad) or f"exit {p.returncode}",
                           message="doctor.sh reported problems")


@static_check("program is a valid PSX-EXE with main and done",
              hint="Keep the .include of common/psxexe.inc and the main/done labels.")
def _(ctx):
    ctx.require_symbols("main", "done")
    probs = ctx.exe.problems()
    expect_true(not probs, "a valid PSX-EXE header", "; ".join(probs))


@check("color.txt holds a colour that is not the starter default",
       hint="Pick your own colour: edit RED/GREEN/BLUE in main.s and record it in color.txt.")
def _(ctx):
    rgb = read_color(ctx)
    change = max(abs(a - b) for a, b in zip(rgb, DEFAULT_RGB))
    expect_true(change >= MIN_CHANGE,
                f"a colour other than 204080 (some channel at least {MIN_CHANGE} away)",
                "%02X%02X%02X" % rgb,
                hint="Choose a clearly different colour; values within a few steps of 204080 "
                     "look identical on a PS1 and cannot prove you changed main.s.")


@check("program reaches `done` without hanging",
       hint="An infinite loop before `done` or a crash stops the run; use -v to see the emulator log.")
def _(ctx):
    ctx.result.require_break()


@check("screen is one flat colour covering the whole display",
       hint="Check the GP0(02h) fill: top-left 0,0 and size 0x00F00140 (320x240).")
def _(ctx):
    img = ctx.result.screenshot()
    expect_true(img.width >= 300 and img.height >= 230, "a ~320x240 display",
                f"{img.width}x{img.height}",
                hint="Did the GP1 display setup commands survive? Keep them in main.")
    px = img.pixel(img.width // 2, img.height // 2)
    expect_region(img, 0, 0, img.width, img.height, px, tol=8, min_fraction=0.99)


@check("screen colour matches color.txt",
       hint="The colour in main.s (RED/GREEN/BLUE) and color.txt must be the same RRGGBB value.")
def _(ctx):
    rgb = read_color(ctx)
    img = ctx.result.screenshot()
    expect_pixel_differs(img, img.width // 2, img.height // 2, DEFAULT_RGB, tol=8,
                         what="centre pixel (vs. the starter's 204080)",
                         hint="The screen still shows the starter colour: edit RED/GREEN/BLUE in main.s and rebuild.")
    expect_pixel(img, img.width // 2, img.height // 2, rgb, tol=10)
    expect_region(img, 0, 0, img.width, img.height, rgb, tol=10, min_fraction=0.99)
