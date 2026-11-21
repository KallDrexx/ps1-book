#!/usr/bin/env python3
"""Mutation test of the verifier (README 8): each mutant is a plausible WRONG implementation made by editing a copy of solution/; verify.sh must exit 1 on it.

  python3 mutants.py              every mutant (about 2.5 minutes each: a full verify.sh run)
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
    "no_drag": ("handling.c", "return speed - fx_mul(speed, scaled(handling_cfg.drag, dt));", "return speed;", "the speed is never reduced by air resistance"),
    "drag_ignores_dt": ("handling.c", "return speed - fx_mul(speed, scaled(handling_cfg.drag, dt));", "return speed - fx_mul(speed, handling_cfg.drag);", "drag per tick, not scaled by dt (PAL runs a different game)"),
    "skid_fraction_unclamped": ("handling.c", "return f > 4096 ? 4096 : f;", "return f;", "a long PAL tick overshoots the target"),
    "no_skid": ("handling.c", "vel[i] += fx_mul(target[i] - vel[i], g);", "vel[i] = target[i];", "the velocity equals forward * speed again"),
    "skid_flat_only": ("handling.c", "\tfor (int i = 0; i < 3; i++)\n\t\tvel[i] += fx_mul", "\tfor (int i = 0; i < 2; i++)\n\t\tvel[i] += fx_mul", "the skid forgets one axis"),
    "pitch_linear_scan": ("handling.c", "\twhile (lo < hi) {", "\tfor (lo = -PITCH_LIMIT; lo <= PITCH_LIMIT && isin(lo) + y < 0; lo++)\n\t\t;\n\twhile (lo < hi && 0) {", "513 evaluations on every tick"),
    "pitch_wrong_sign": ("handling.c", "g = (-num) / up[1];", "g = num / up[1];", "the nose tilts against the slope"),
    "pitch_never_applied": ("game.c", "\t\t\thandling_auto_pitch(&ship, &track, ship_section, dt_scale);\n", "", "auto-pitch is never called"),
    "step_by_index": ("race.c", "\tif (p->next == cur)\n\t\treturn 1;\n\tif (p->prev == cur)\n\t\treturn -1;\n\treturn 0;",
                      "\t(void) p;\n\tif (cur == prev + 1 || (prev == t->section_count - 1 && cur == 0))\n\t\treturn 1;\n\tif (cur == prev - 1 || (prev == 0 && cur == t->section_count - 1))\n\t\treturn -1;\n\treturn 0;",
                      "ring steps by index arithmetic instead of the links"),
    "lap_length_hard_coded": ("race.c", "(r->lap + 1) * t->section_count", "(r->lap + 1) * 112", "a lap is 112 sections whatever the track"),
    "reverse_not_subtracted": ("race.c", "\tr->progress += step;", "\tr->progress += step > 0 ? step : 0;", "driving backward over the line and forward again counts a lap"),
    "wrong_way_latches": ("race.c", "\tr->wrong_way = r->furthest - r->progress >= limit;", "\tif (r->furthest - r->progress >= limit)\n\t\tr->wrong_way = 1;", "the warning never clears"),
    "new_best_on_tie": ("race.c", "if (race_best == 0 || best < race_best) {", "if (race_best == 0 || best <= race_best) {", "equalling the best lap is a new best"),
    "best_not_kept": ("race.c", "\t\t\t\trace_best = best;\n", "", "the best lap is forgotten at once"),
    "countdown_off_by_one": ("race.c", "if (r->cd_ticks >= cf * hz)", "if (r->cd_ticks > cf * hz)", "the countdown lasts one tick too long"),
    "no_lap_chime": ("game.c", "\t\t\tif (ev & RACE_LAP)\n\t\t\t\taudio_play_sfx(SMP_BEEP);\n", "", "no sound at a lap"),
    "restart_keeps_the_race": ("game.c", "\t\trace_reset(&race);                                      /* Chapter 41: a new race, a new clock */\n", "", "a restart continues the old clock and laps"),
    "seconds_unpadded": ("race.c", '"%d:%02d.%02d"', '"%d:%d.%02d"', "7 seconds prints as 0:7.05"),
    "results_start_restarts": ("game.c", "\t\tif (input_pressed(INPUT_START))\n\t\t\tset_state(STATE_TITLE);\n\t\telse if (input_pressed(INPUT_CROSS))", "\t\tif (input_pressed(INPUT_START))\n\t\t\tset_state(STATE_COUNTDOWN);\n\t\telse if (input_pressed(INPUT_CROSS))", "START on the results restarts instead of leaving"),
}


def run(name):
    f, old, new, what = MUTANTS[name]
    work = Path(tempfile.mkdtemp(prefix=f"ch41mut-{name}-"))
    try:
        proj = work / "p"
        shutil.copytree(SOLUTION, proj, ignore=shutil.ignore_patterns("build"))
        text = (proj / f).read_text()
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
