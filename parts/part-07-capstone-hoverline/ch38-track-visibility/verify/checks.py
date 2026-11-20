"""Chapter 38 checks: Track Visibility (the nearest section, a window of sections, a readout).
Build: CMake + PSn00bSDK; the CMake rule runs tools/assets/mkassets.py. The emulator BOOTS THE .cue.
HOW THE LAP IS DRIVEN (README 5.9): the ship has no collision yet and flies straight, so a lap cannot be driven by the pad. The probe (probe.lua) writes the ship's pose
(pos, yaw; speed 0) at the end of every frame; the pad is idle, so ship_update leaves it alone; the game then updates the section and draws; at the next frame_done the
probe records the row: ship_section, the counters, the vertex states, the packets of the frame's ordering table, the frame's work in CPU cycles.
THE POSES come from the generated .TRK (centre line, section frames): a smooth run with lateral sway across the lap boundary, a fast stretch (several sections per frame),
teleports, a run BACKWARDS, an off-road excursion, a stretch 150,000 units away (squares above 32 bits) and a full lap; the alt disc is track 2 translated by (+60000, 0, +45000) with a different script.
THE MODEL: example/vis_ref.py (the exact metric in Python integers, brute force, the window).
Runs: main (track 1, defaults), whole (the same poses with the window wider than the track: the cost of drawing everything), narrow (vis_ahead 9, vis_behind 2),
alt (track 2 translated), list (vis_mode 1, only when vis_list_done is 1)."""

import atexit
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from harness import *

ROOT_DIR = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "tools" / "assets"))
sys.path.insert(0, str(HERE.parent / "example"))
import mkassets      # noqa: E402
import formats       # noqa: E402
import vis_ref as M  # noqa: E402

W, H = 320, 240
BG = (24, 24, 48)
VBLANK_NTSC = 566120          # CPU cycles between two vertical blanks (measured in the Chapter 37 verifier)
WORK_LIMIT = 540000           # a frame's work must stay below this (about 4.6% under one blank)
UPDATE_LIMIT = 8000           # cycles of one track_nearest_update that needs no full search (measured: <= 2400; a full search over 112 sections: 17,600 and up)
PRIM_LIMIT = 170              # packets for the track and the ship in one frame of the default window (measured: <= 130)
MAX_FRAMES = 2400
SHIFT = (60000, 0, 45000)

config(
    title="Track Visibility: nearest section, windowed rendering, readout",
    build="cmake", exe="game.exe", sym="", elf="game.elf", iso="hoverline.cue",
    break_at=None, max_frames=MAX_FRAMES, timeout=420, vram=True,
)

_TMP = Path(tempfile.mkdtemp(prefix="ch38ref-"))
atexit.register(shutil.rmtree, _TMP, True)
FILES, MANIFESTS = mkassets.build(_TMP / "assets", seed=1)
TRK1 = formats.parse_trk(FILES["TRACK.TRK"])
MAN1 = MANIFESTS["TRACK.TRK"]


def make_alt_track():
    """Track 2, translated far from the origin (every absolute x and z above 16 bits, differences of squares above 32 bits)."""
    t = formats.parse_trk(FILES["TRACK2.TRK"])
    verts = [(x + SHIFT[0], y + SHIFT[1], z + SHIFT[2]) for x, y, z in t["vertices"]]
    secs = []
    for s in t["sections"]:
        s = dict(s)
        s["centre"] = tuple(c + d for c, d in zip(s["centre"], SHIFT))
        secs.append(s)
    faces = [dict(f, color=(0, 0, 0)) for f in t["faces"]]
    vis = [s["vis"] for s in t["sections"]]
    total = sum(s["length"] for s in secs)
    return formats.build_trk("TRACK2S", verts, faces, secs, vis, t["start_section"], total, t["texture_count"])


ALT_BIN = make_alt_track()
TRK2 = formats.parse_trk(ALT_BIN)


# ---- the scripted laps ---------------------------------------------------------------------------------------------------------------------------
def interp(trk, u, lat, hover=120):
    """The point u sections along the centre line (u = i is section i's centre), `lat` units to the right, `hover` above the road."""
    secs = trk["sections"]
    n = len(secs)
    i0 = math.floor(u)
    f = u - i0
    a, b = secs[i0 % n], secs[(i0 + 1) % n]
    near = secs[round(u) % n]
    p = []
    for k in range(3):
        c = a["centre"][k] + (b["centre"][k] - a["centre"][k]) * f
        c += (near["right"][k] * lat) / 4096 + (near["up"][k] * hover) / 4096
        p.append(round(c))
    d = [b["centre"][k] - a["centre"][k] for k in range(3)]
    return p, M.heading(d[0], d[2])


def make_poses(trk, script):
    """script: ('run', u0, u1, step, sway) | ('tele', u) | ('hold', frames) | ('off', u, max_lat, frames) | ('far', u, lat, frames). Returns dicts x, y, z, yaw, kind."""
    out = []

    def add(u, lat, kind, flip=False):
        p, yaw = interp(trk, u, lat)
        out.append(dict(x=p[0], y=p[1], z=p[2], yaw=(yaw + 2048) % 4096 if flip else yaw, kind=kind, u=u))

    for seg in script:
        if seg[0] == "run":
            _, u0, u1, step, sway = seg
            k, u = 0, u0
            while (u - u1) * (1 if step > 0 else -1) < 0:
                add(u, sway * math.sin(k * 0.45), "run", step < 0)
                u += step
                k += 1
        elif seg[0] == "tele":
            add(seg[1], 150, "tele")
        elif seg[0] == "hold":
            for _ in range(seg[1]):
                add(out[-1]["u"], 0, "hold")
        elif seg[0] == "far":
            _, u, lat, frames = seg
            for k in range(frames):
                add(u + 0.9 * k, lat, "far")
        elif seg[0] == "off":
            _, u, mx, frames = seg
            for k in range(frames):
                add(u, mx * math.sin(math.pi * k / (frames - 1)), "off")
    return out


def script_main(n):
    return [("run", n - 14, n + 20, 0.4, 350),          # across the lap boundary (section n-1 -> 0), swaying across the road
            ("run", 20, 20 + 26, 6.5 / 3, 0),            # fast: 2.2 sections per frame
            ("run", 46, 46 + 16, 6.5, 0),                # faster: more than the walk's step limit
            ("tele", 70), ("run", 70, 82, 0.4, 250),     # teleport, then on
            ("run", 82, 62, -0.5, 200),                  # backwards
            ("tele", 5), ("hold", 6),                    # teleport near the start and stay put
            ("off", 31, 6000, 14),                       # off the road and back (beyond vis_lost in the middle)
            ("far", 31, 150000, 6),                      # far away: d above 65535, its square above 32 bits
            ("tele", n - 2), ("run", n - 2, n + 6, 0.35, 150),
            ("run", 0, n, 1.0, 300)]                     # a whole lap at one section per frame


def script_alt(n):
    return [("run", 40, 40 + 18, 0.33, 450),
            ("tele", n - 3), ("run", n - 3, n + 9, 0.7, 300),     # across the boundary
            ("run", 55, 55 + 12, 3.2, 0),                           # fast
            ("tele", 18), ("run", 18, 6, -0.45, 250),               # backwards
            ("tele", 90), ("hold", 4), ("off", 95, 5000, 12), ("far", 60, -120000, 6),
            ("run", 0, n, 1.5, 250)]


def pose_list(trk, script):
    return make_poses(trk, script(len(trk["sections"])))


POSES = {"main": pose_list(TRK1, script_main), "alt": pose_list(TRK2, script_alt)}
POSES["whole"] = POSES["main"][:110]
POSES["narrow"] = POSES["main"][:150]
POSES["list"] = POSES["main"][:150]
TRACKS = {"main": TRK1, "whole": TRK1, "narrow": TRK1, "list": TRK1, "alt": TRK2}


def pose_pos(p):
    return [p["x"], p["y"], p["z"]]


def lua_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, dict):
        return "{" + ",".join(f"[{json.dumps(k)}]={lua_val(x)}" for k, x in v.items()) + "}"
    return "{" + ",".join(lua_val(x) for x in v) + "}"


def prim_buf_size(project):
    text = (Path(project) / "psxe" / "include" / "psxe" / "ot.h").read_text()
    m = re.search(r"#define\s+PRIM_BUF_SIZE\s+(\d+)", text)
    return int(m.group(1)) if m else 2048


def params_for(name, project, patch=None):
    shots = {"main": [["lap", 60], ["fast", 135]], "alt": [["alt", 30]]}.get(name, [])
    d = {"poses": [[p["x"], p["y"], p["z"], p["yaw"]] for p in POSES[name]], "patch": patch or {}, "shots": shots,
         "frame_sz": 64 * 4 + prim_buf_size(project) + 16, "vertex_count": len(TRACKS[name]["vertices"]), "end_frame": MAX_FRAMES - 100}
    return d


def probe_gen(ctx, name, patch=None):
    gen = ctx.work / f"probe_{name}.lua"
    gen.write_text("PARAMS = " + lua_val(params_for(name, ctx.project, patch)) + "\ndofile(" + json.dumps(str(HERE / "probe.lua")) + ")\n")
    return gen


# the default run's PARAMS go through the environment (the default run starts before any check)
_def = _TMP / "params_main.lua"
_def.write_text("PARAMS = " + lua_val(params_for("main", HERE.parent / "starter")) + "\n")   # frame size from the starter's PRIM_BUF_SIZE (the same in solution/)
os.environ["CH38_PARAMS"] = str(_def)


def alt_disc(ctx):
    bdir = ctx.build.build_dir
    if (bdir / "alt.cue").exists():
        return
    xml = next(iter(sorted(bdir.glob("cd_image_*.xml"))), None)
    if xml is None:
        raise CheckFailure(expected="CMake's configured iso xml", actual="not found", hint="Use psn00bsdk_add_cd_image.")
    (bdir / "alt").mkdir(exist_ok=True)
    (bdir / "alt" / "TRACK.TRK").write_bytes(ALT_BIN)
    text, k = re.subn(r'(<file\s+name="TRACK.TRK"[^>]*?source=")[^"]*(")', lambda m: m.group(1) + str(bdir / "alt" / "TRACK.TRK") + m.group(2), xml.read_text(), flags=re.I)
    expect_eq(k, 1, "iso.xml has one <file name=\"TRACK.TRK\" source=...> entry", hint="Appendix E.2: the track lives in <dir name=\"DATA\">.")
    (bdir / "alt.xml").write_text(text)
    p = subprocess.run(["mkpsxiso", "-y", "-q", "-o", "alt.bin", "-c", "alt.cue", "alt.xml"], cwd=bdir, capture_output=True, text=True, timeout=60, env=tool_env())
    expect_eq(p.returncode, 0, "mkpsxiso builds the alternative disc", hint=(p.stdout + p.stderr)[-400:])


PATCHES = {"whole": {"vis_ahead": 500, "vis_behind": 500}, "narrow": {"vis_ahead": 9, "vis_behind": 2}, "list": {"vis_mode": 1}, "alt": {}}


def run_of(ctx, name):
    if name == "main":
        r = ctx.result
    else:
        kw = dict(probe=probe_gen(ctx, name, PATCHES[name]))
        if name == "alt":
            alt_disc(ctx)
            kw["iso"] = "alt.cue"
        r = ctx.run(name, **kw)
    r.require_finished()
    exc = r.record("exception")
    if exc:
        raise CheckFailure(expected="no CPU exception", actual=f"CPU exception {exc['code']} at pc 0x{exc['epc']:08X}, address 0x{exc['badvaddr']:08X}",
                           hint="A load through a NULL or dangling pointer, or an index outside the section table (section -1?).")
    info = r.record("info")
    expect_true(info is not None and info.get("load_status") == 0, "the program loads everything and enters the game", f"status {r.data.get('status')}, info {info}",
                hint="Does it hang in cd_load_file? Booting + loading takes about 400 emulated frames.")
    rows = r.record("rows") or []
    expect_true(len(rows) == len(POSES[name]), f"{name}: one row per pose ({len(POSES[name])})", f"{len(rows)} rows", "Does the program run a frame after every pose? (frame_done must be called once per loop.)")
    return r, rows


def ref_of(name):
    """Per pose: the brute-force section, d2 of it, and whether the incremental rule needs a full search there."""
    trk = TRACKS[name]
    secs = trk["sections"]
    res, prev = [], None
    for p in POSES[name]:
        pos = pose_pos(p)
        s = M.nearest(secs, pos)
        d = M.d2(secs[s]["centre"], pos)
        if prev is None:
            need = True
        else:
            _, need = M.update(secs, pos, prev)
        res.append((s, d, need))
        prev = s
    return res


REF = {k: ref_of(k) for k in ("main", "alt")}
for k in ("whole", "narrow", "list"):
    REF[k] = REF["main"][:len(POSES[k])]


def show(v):
    return "(" + ", ".join(str(x) for x in v) + ")"


# ---- checks -------------------------------------------------------------------------------------------------------------------------------------
def check_poked(rows, name):
    for k, row in enumerate(rows):
        p = POSES[name][k]
        if list(row["ship"]) != pose_pos(p):
            raise CheckFailure(expected=f"ship.pos {show(pose_pos(p))} at pose {k}", actual=show(row["ship"]),
                               hint="The pad is idle: ship_update must not move the ship at speed 0 (is something else writing ship.pos?).")


def nearest_report(rows, name):
    ref = REF[name]
    bad = [k for k, row in enumerate(rows) if row["section"] != ref[k][0]]
    return bad, ref


@check("starts_in_the_game", hint="START on the title enters the game; ship_section is set on entering (brute force over every section).")
def _(ctx):
    r, rows = run_of(ctx, "main")
    st = r.record("info")["start_row"]
    n = TRK1["sections"]
    expect_true(st is not None, "the game state was entered", "never", "Press START on the title: set_state(STATE_GAME).")
    ship = [x for x in st["ship"][:3]]
    want = M.nearest(TRK1["sections"], ship)
    expect_eq(st["section"], want, f"ship_section when the game starts (ship at {show(ship)}: the section nearest to it, by brute force)",
              hint="track_nearest_brute: the smallest squared distance to a section centre, the lowest index on a tie.")
    check_poked(rows, "main")


def nearest_check(ctx, name):
    r, rows = run_of(ctx, name)
    n = len(TRACKS[name]["sections"])
    check_poked(rows, name)
    for k, row in enumerate(rows):
        expect_true(0 <= row["section"] < n, f"{name} pose {k}: ship_section in 0..{n - 1}", str(row["section"]), "Wrap with the next/prev links; never index outside the table.")
    bad, ref = nearest_report(rows, name)
    frac = 1 - len(bad) / len(rows)
    kinds = [p["kind"] for p in POSES[name]]
    first = ", ".join(f"pose {k} ({kinds[k]}): got {rows[k]['section']}, want {ref[k][0]}" for k in bad[:4])
    expect_true(frac >= 0.99, f"{name}: ship_section equals the brute-force nearest section on >= 99% of the {len(rows)} frames", f"{frac:.1%} ({len(bad)} wrong; {first})",
                "Metric: squared 3D distance to the section centre, 64-bit; ties go to the lowest index. Update through next/prev, brute force after a teleport.")
    for k in bad:
        expect_true(k + 1 not in bad, f"{name}: a wrong frame is followed by a right one (recovery within one frame)", f"poses {k} and {k + 1} both wrong ({first})",
                    "After a jump (more than VIS_MAX_STEPS sections) or when the section is farther than vis_lost, search every section.")
    return r, rows


@check("nearest_section_main_lap", hint="One lap of track 1: smooth running across the lap boundary (section n-1 -> 0), a fast stretch, teleports, a run backwards, an off-road excursion.")
def _(ctx):
    r, rows = nearest_check(ctx, "main")
    bad, ref = nearest_report(rows, "main")
    expect_true(not bad, "main lap: every frame matches the exact brute-force reference", f"{len(bad)} wrong, first at pose {bad[:1]}",
                "With the update rule of track_vis.h the result IS the brute-force answer for these poses; a mismatch is a bug in the metric, the tie rule or the wrap.")


@check("teleports_recover", hint="After a teleport (a jump of many sections) the very next frame's answer must be right: brute force when the neighbour walk gives up.")
def _(ctx):
    r, rows = run_of(ctx, "main")
    ref = REF["main"]
    kinds = [p["kind"] for p in POSES["main"]]
    tele = [k for k, kd in enumerate(kinds) if kd == "tele"]
    expect_true(len(tele) >= 3, "the script has teleports", str(len(tele)), "")
    for k in tele:
        for j in (k, k + 1):
            if j < len(rows):
                expect_eq(rows[j]["section"], ref[j][0], f"ship_section at pose {j} ({'the teleport' if j == k else 'the frame after it'})",
                          hint="A jump over more than VIS_MAX_STEPS sections must fall back to the full search (and so must a result beyond vis_lost).")


@check("update_uses_the_links_not_the_whole_track", hint="Normal frames walk the neighbours (a few hundred cycles); the full search runs only when it must (teleports, fast flight, off the road).")
def _(ctx):
    r, rows = run_of(ctx, "main")
    ref = REF["main"]
    need = sum(1 for k in range(len(ref)) if ref[k][2])
    brute = rows[-1]["brute"] - rows[0]["brute"] + 1
    expect_true(rows[-1]["brute"] <= need + 3, f"full searches over the lap: at most the {need} frames that need one (+ the start and 2 spare)", f"{rows[-1]['brute']} searches",
                "Searching every frame is correct but is exactly what the incremental update avoids: test the section and its neighbours first.")
    upd = r.record("upd") or []
    expect_true(len(upd) >= len(rows) - 2, "track_nearest_update is called once per game frame", f"{len(upd)} calls for {len(rows)} frames", "game_update: ship_section = track_nearest_update(...) after chase_camera_update.")
    cheap = sorted(u["cyc"] for u in upd if u["brute"] == 0)
    expect_true(len(cheap) >= len(rows) // 2, "most frames update without a full search", f"{len(cheap)} of {len(upd)}", "")
    worst = cheap[-1]
    expect_true(worst <= UPDATE_LIMIT, f"an update without a full search takes <= {UPDATE_LIMIT} cycles (worst {worst}, median {cheap[len(cheap) // 2]})",
                f"{worst}", "Three distances (the section, next, prev) per step; no loop over every section on a normal frame.")


def window_check(rows, name, ahead, behind):
    trk = TRACKS[name]
    secs, faces = trk["sections"], trk["faces"]
    n = len(secs)
    nv = len(trk["vertices"])
    for k, row in enumerate(rows):
        s = row["section"]
        if not 0 <= s < n:
            continue
        first, count = M.window(n, s, ahead, behind)
        where = f"{name} pose {k} (section {s}, ahead {ahead}, behind {behind})"
        expect_eq((row["first"], row["count"]), (first, count), f"{where}: window (first, count)",
                  hint="Sections s - behind .. s + ahead modulo the section count: first = (s - behind) mod n, count = behind + ahead + 1, or the whole track.")
        st = row["stats"]
        expect_eq(st[0], 5 * count, f"{where}: faces seen by track_draw (5 per section)", hint="Draw exactly the window: nothing more, nothing less.")
        expect_eq(sum(st[1:7]), st[0], f"{where}: every face in exactly one bucket", hint="Chapter 34's buckets are unchanged.")
        want = set()
        for j in range(count):
            sec = secs[(first + j) % n]
            for f in faces[sec["first_face"]:sec["first_face"] + sec["face_count"]]:
                want.update(f["v"])
        got = {i for i, c in enumerate(row["vs"]) if c != "0"}
        if got != want:
            extra, miss = sorted(got - want), sorted(want - got)
            raise CheckFailure(expected=f"{where}: vertices touched = those of sections {first}..{(first + count - 1) % n}", actual=f"{len(extra)} extra {extra[:4]}, {len(miss)} missing {miss[:4]}",
                               hint="track_draw(first, count): the window wraps at the end of the loop (use modulo), and section s itself is inside it.")


@check("window_rule_main", hint="Each frame draws exactly sections s - 4 .. s + 24 around the reader's own ship_section, wrapped at the lap boundary: checked on the vertices track_draw touched.")
def _(ctx):
    r, rows = run_of(ctx, "main")
    window_check(rows, "main", rows[0]["ahead"], rows[0]["behind"])
    expect_eq((rows[0]["ahead"], rows[0]["behind"]), (24, 4), "default vis_ahead / vis_behind (the manifest's vis_rule)", hint="VIS_AHEAD 24, VIS_BEHIND 4.")
    wrap = [k for k, row in enumerate(rows) if row["first"] + row["count"] > len(TRK1["sections"]) and row["count"] < len(TRK1["sections"])]
    expect_true(len(wrap) >= 20, "the lap exercises windows that wrap past the last section", f"{len(wrap)} frames", "")


@check("window_rule_patched", hint="vis_ahead = 9, vis_behind = 2 (patched at main's entry): nothing is hard-coded.")
def _(ctx):
    r, rows = run_of(ctx, "narrow")
    window_check(rows, "narrow", 9, 2)
    window_check(run_of(ctx, "whole")[1][:20], "whole", 500, 500)


@check("prim_counts", hint="prims_this_frame = the packets linked for the track and the ship (before the readout); it equals the packets of the table minus the readout's characters.")
def _(ctx):
    r, rows = run_of(ctx, "main")
    for k, row in enumerate(rows):
        hist = {int(c): v for c, v in row["hist"].items()}
        font = sum(v for c, v in hist.items() if c in (0x74, 0x75, 0x76, 0x77, 0x7C, 0x7D, 0xE1))
        total = sum(hist.values()) - font
        expect_eq(row["prims"], total, f"pose {k}: prims_this_frame vs the packets of the frame's ordering table (readout excluded)",
                  hint="Count the packets linked by the track and the ship: prims_submitted after draw_ship, before FntSort.")
        ship = row["prims"] - row["stats"][6]
        expect_true(0 <= ship <= 40, f"pose {k}: the ship's packets (prims - faces drawn) are plausible", str(ship), "")
    mx = max(row["prims"] for row in rows)
    expect_true(mx <= PRIM_LIMIT, f"at most {PRIM_LIMIT} packets in any frame of the lap (most: {mx})", str(mx), "The window must be the default 24 ahead / 4 behind, not the whole track.")
    for g in r.record("guards"):
        expect_eq(list(g.values()) if isinstance(g, dict) else g, [0xA5] * 16, "the primitive buffer's guard bytes", hint="A packet written past the buffer.")


@check("frame_budget_main", hint="Every frame of the lap is finished before the next vertical blank: one blank per frame, work under the limit.")
def _(ctx):
    r, rows = run_of(ctx, "main")
    bad = [(k, rows[k]["vbl"] - rows[k - 1]["vbl"]) for k in range(1, len(rows)) if rows[k]["vbl"] - rows[k - 1]["vbl"] != 1]
    expect_true(not bad, "one vertical blank between consecutive frames of the lap (60 fps)", f"{len(bad)} frames took longer, first {bad[:3]}",
                "Draw less: a window of 24 + 4 + 1 sections, subdivision off (R1 toggles it; it costs 65% more).")
    works = [row["work"] for row in rows]
    expect_true(min(works) > 0, "every frame's work was measured", "no VSync(0) call seen", "display_swap calls VSync(0).")
    expect_true(max(works) <= WORK_LIMIT, f"the busiest frame's work <= {WORK_LIMIT} cycles of {VBLANK_NTSC}", f"{max(works)} (pose {works.index(max(works))})", "Window too wide, or something slow in the update.")


@check("window_is_cheaper_than_the_whole_track", hint="Same poses with vis_ahead = vis_behind = 500 (the window wider than the track): the whole track costs more cycles per frame.")
def _(ctx):
    r, rows = run_of(ctx, "main")
    rw, whole = run_of(ctx, "whole")
    a = sum(row["work"] for row in rows[:len(whole)]) / len(whole)
    b = sum(row["work"] for row in whole) / len(whole)
    expect_true(a < 0.85 * b, "the windowed frame costs under 85% of the whole-track frame (mean over the same poses)", f"window {a:.0f} vs whole {b:.0f} cycles",
                "Is the window really 29 sections out of 112?")
    expect_true(max(row["count"] for row in whole) == len(TRK1["sections"]), "the whole-track run draws every section", str(max(row["count"] for row in whole)), "")


@check("alt_disc_track_2_translated", hint="Track 2 (104 sections) translated by (+60000, 0, +45000): squared distances do not fit 32 bits, the lap boundary is at another index, nothing may be hard-coded.")
def _(ctx):
    r, rows = nearest_check(ctx, "alt")
    bad, ref = nearest_report(rows, "alt")
    expect_true(not bad, "alt lap: every frame matches the reference", f"{len(bad)} wrong, first at pose {bad[:1]}", "Use 64-bit squared distances (s64 differences).")
    window_check(rows, "alt", 24, 4)
    for k, row in enumerate(rows):
        expect_true(row["work"] <= WORK_LIMIT, f"alt pose {k}: frame work <= {WORK_LIMIT}", str(row["work"]), "")


# ---- the readout -----------------------------------------------------------------------------------------------------------------------------------
@check("readout_text", hint="vis_text holds 'SEC nnn  PRIMS nnnn' (printf %3d / %4d) from ship_section and prims_this_frame of the same frame.")
def _(ctx):
    r, rows = run_of(ctx, "main")
    for k, row in enumerate(rows):
        want = "SEC %3d  PRIMS %4d" % (row["section"], row["prims"])
        expect_eq(row["text"], want, f"pose {k}: the readout line", hint="vis_readout_format: snprintf(vis_text, ..., \"SEC %3d  PRIMS %4d\", ship_section, prims_this_frame).")


@check("readout_on_screen", hint="The text is on the screen at (8, 8), in the SDK font, over the track: white characters in the top-left corner.")
def _(ctx):
    r, rows = run_of(ctx, "main")
    shots = r.record("shots")
    expect_true(len(shots) == 2, "two screenshots taken", str(len(shots)), "")
    font = r.vram().rect(960, 0, 32, 32)
    expect_true(sum(1 for b in font if b) > 100, "the SDK font is in VRAM at x 960..991, y 0..31 (FntLoad(960, 0))", "that area is empty", "Call FntLoad(960, 0) once after the display is initialised.")
    for sh in shots:
        img = r.screenshot(sh["name"])
        row = rows[sh["row"] - 1]
        text = row["text"]
        # the line is 8 pixel rows high at y = 8..15; each character is an 8 x 8 cell starting at x = 8
        bright = 0
        cells = 0
        for i, ch in enumerate(text):
            if ch == " ":
                continue
            cells += 1
            x0 = 8 + 8 * i
            n = sum(1 for y in range(8, 16) for x in range(x0, x0 + 8) if min(img.pixel(x, y)) >= 200)
            if n >= 6:
                bright += 1
        expect_true(cells > 0 and bright >= cells - 1, f"{sh['name']}: every character cell of '{text}' holds white pixels at (8 + 8 i, 8)", f"{bright} of {cells} cells",
                    "FntLoad(960, 0) once; FntSort(slot 0 of the table, ...) each frame, after the track and the ship.")
        # the area right of the text is not text: no white pixels beyond the line's end
        end = 8 + 8 * len(text) + 8
        stray = sum(1 for y in range(8, 16) for x in range(end, min(W, end + 24)) if min(img.pixel(x, y)) >= 200)
        expect_true(stray <= 8, f"{sh['name']}: nothing bright just after the text's end", f"{stray} pixels", "")


# ---- the visibility list (stretch) -----------------------------------------------------------------------------------------------------------------
@check("stretch_visibility_list", hint="Stretch: vis_list_done = 1 and track_draw_list draws exactly the sections of the section's .TRK visibility slice (vis_mode = 1).")
def _(ctx):
    done = ctx.result.record("info").get("vis_list_done")
    if done != 1:
        print("  (stretch goal not attempted: vis_list_done = 0; this check is skipped)")
        return
    r, rows = run_of(ctx, "list")
    trk = TRK1
    secs, faces = trk["sections"], trk["faces"]
    for k, row in enumerate(rows):
        s = row["section"]
        lst = secs[s]["vis"]
        expect_eq(row["count"], len(lst), f"list pose {k}: sections drawn = the slice's length", hint="vis_count = the slice's vis_count.")
        want = set()
        for j in lst:
            sec = secs[j]
            for f in faces[sec["first_face"]:sec["first_face"] + sec["face_count"]]:
                want.update(f["v"])
        got = {i for i, c in enumerate(row["vs"]) if c != "0"}
        expect_eq(sorted(got), sorted(want), f"list pose {k}: the vertices of the listed sections", hint="track_draw_begin once, then track_draw_section for every entry of vis[vis_first .. vis_first + vis_count - 1].")
    mx = max(row["work"] for row in rows)
    expect_true(mx <= WORK_LIMIT, f"list mode keeps the frame under {WORK_LIMIT} cycles", str(mx), "")

