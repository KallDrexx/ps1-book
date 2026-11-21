#!/usr/bin/env python3
"""Mutation test of the verifier (README 8): each mutant is a plausible WRONG implementation made by editing a copy of solution/; verify.sh must exit 1 on it.

  python3 mutants.py              every mutant (about 2.5 minutes each)
  python3 mutants.py NAME ...     only those

Prints, per mutant, the exit code and the checks that failed. It is not part of tools/ci.sh (the CI proves solution passes and starter fails)."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOLUTION = HERE.parent / "solution"

# name: (file, old text, new text, what it models)
MUTANTS = {
    "nearest_centre": ("collide.c", "\tcur = walk(t, cur, pos, &ok);\n\tif (ok)\n\t\treturn cur;\n\treturn walk(t, track_nearest_brute(t, pos), pos, &ok);",
                       "\t(void) cur; (void) ok;\n\treturn track_nearest_brute(t, pos);", "Chapter 38's answer instead of the ring-line walk"),
    "no_yaw_correction": ("collide.c", "s->yaw = (s->yaw + fx_mul(err, c->yaw_fix)) & ANGLE_MASK;", "(void) err;", "damps the speed but never turns the ship"),
    "unwrapped_yaw_error": ("collide.c", "int32_t err = ((target - s->yaw + HALF) & ANGLE_MASK) - HALF;", "int32_t err = target - s->yaw;", "turns the long way round"),
    "push_by_radius": ("collide.c", "depth = c->radius - d[k];", "depth = c->radius;", "pushes by the whole radius, not by the penetration"),
    "damp_ignores_angle": ("collide.c", "fx_mul(c->wall_damp, impact)", "c->wall_damp", "a glancing hit costs as much as a head-on one"),
    "boost_every_tick": ("collide.c", "if (on && !st->on_boost) {", "if (on) {", "the impulse is not edge-triggered"),
    "boost_by_section": ("collide.c", "int on = f && (f->flags & TRK_BOOST) ? 1 : 0;", "int on = audio_section_boost(t, ship_section);", "Chapter 39's rule: the section, not the face under the ship"),
    "thud_clock_on_thuds_only": ("collide.c", "\t\t\tresult |= COLL_THUD;\n\t\t}\n\t\tst->last_hit = ship_ticks;", "\t\t\tresult |= COLL_THUD;\n\t\t\tst->last_hit = ship_ticks;\n\t\t}", "sliding along a wall thuds every thud_gap ticks"),
    "ground_sign": ("collide.c", "return s->centre[1] + (-num) / uy;", "return s->centre[1] + num / uy;", "the surface tilts the wrong way"),
    "no_hover": ("collide.c", "s->pos[1] = collide_ground(t, ship_section, s->pos) - ship_cfg.hover;", "s->pos[1] = collide_ground(t, ship_section, s->pos);", "the ship rides on the road"),
    "slow_heading": ("collide.c", "collide_heading(edge[k][0], edge[k][1])", "heading_angle(edge[k][0], edge[k][1])", "4096 evaluations on every hit"),
    "edge_side_ignored": ("collide.c", "s = ex * clamp_d(seg[5] - seg[1]) - ez * clamp_d(seg[4] - seg[0]) < 0 ? -1 : 1;", "s = 1;", "distances positive on the wrong side for half the edges"),
    "no_respawn": ("collide.c", "if (d[0] < -c->off_limit || d[1] < -c->off_limit) {", "if (0) {", "far outside the road is just pushed back"),
    "parse_into_global": ("trackload.c", "rc = track_parse(file, size, &fresh);", "rc = track_parse(file, size, &track); fresh = track;", "a failed load wipes the running track"),
    "leak_old_image": ("trackload.c", "\tfree(track_image);\n", "", "the old file image is never freed"),
    "no_music_restart": ("trackload.c", "audio_music_start();", "(void) 0;", "the music stops for good after a load"),
}


def run(name):
    f, old, new, what = MUTANTS[name]
    work = Path(tempfile.mkdtemp(prefix=f"ch40mut-{name}-"))
    try:
        proj = work / "p"
        shutil.copytree(SOLUTION, proj, ignore=shutil.ignore_patterns("build"))
        text = (proj / f).read_text()
        if f == "trackload.c" and name == "no_music_restart":
            n = text.count(old)
            text = text.replace(old, new)
        else:
            n = text.count(old)
            assert n == 1, f"{name}: the text to replace occurs {n} times in {f}"
            text = text.replace(old, new)
        (proj / f).write_text(text)
        p = subprocess.run([str(HERE / "verify.sh"), str(proj)], capture_output=True, text=True, timeout=900)
        fails = [l.split()[1] for l in p.stdout.splitlines() if l.startswith("  FAIL")]
        last = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
        print(f"{name:26s} exit {p.returncode}  {'KILLED' if p.returncode == 1 and fails else 'SURVIVED' if p.returncode == 0 else 'ERROR'}  ({what})")
        print(f"{'':26s} {last}; failing: {', '.join(fails)}", flush=True)
        return p.returncode == 1 and bool(fails)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    names = sys.argv[1:] or list(MUTANTS)
    ok = [run(n) for n in names]
    print(f"{sum(ok)} of {len(ok)} mutants killed")
    sys.exit(0 if all(ok) else 1)
