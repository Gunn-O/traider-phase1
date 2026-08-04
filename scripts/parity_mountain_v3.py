#!/usr/bin/env python
# ============================================================================
# scripts/parity_mountain_v3.py — BYTE-IDENTICAL parity gate for Mountain v3
# ----------------------------------------------------------------------------
# Runs the REPO's ported Mountain core (strategies.mountain.MountainV3) INSIDE
# the validated snapshot engine (reference/mountain_v3_snapshot/bt) for BOTH
# configs, and diffs all 5 output files against the golden expected_results.
#
# Because Mountain's decision core is stateful (driven by the engine's on_bar),
# byte-identical trades.csv is only meaningful when the SAME engine drives the
# SAME core — so we swap the repo core into the snapshot registry (the engine
# duck-types the strategy) and let the snapshot's own report writer emit files.
#
# "byte-identical" = content-identical after CRLF→LF normalization (the golden
# files are LF; report.py writes platform-default newlines → CRLF on Windows).
# That is the only platform artifact; every value/row/order must match exactly.
#
# Gate: exit 0 iff BOTH configs produce all 5 files identical to golden.
#   --selfcheck : run the SNAPSHOT's own MountainV3 (proves the plumbing; must PASS)
# ============================================================================
from __future__ import annotations

import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO_ROOT, "reference", "mountain_v3_snapshot")
DATA = os.path.join(SNAP, "data", "XAUUSD_M1_2026-06-09.csv")
GLOBAL = os.path.join(SNAP, "configs", "global.yaml")

# snapshot dir first so `bt` = the vendored Mountain engine; repo root for `strategies`.
sys.path.insert(0, SNAP)
sys.path.insert(0, REPO_ROOT)

FILES = ["trades.csv", "plans.csv", "summary.json", "unfilled.csv", "plan_meta.csv"]
CONFIGS = [
    ("mountain_v3_tpsl",      "mountain_v3_tpsl"),       # (config stem, expected dir)
    ("mountain_v3_tpsl_rr85", "mountain_v3_tpsl_rr85"),
]


def _norm(path: str) -> bytes:
    return open(path, "rb").read().replace(b"\r\n", b"\n")


def _diff_run(out_dir: str, expected_dir: str):
    """returns list of (file, ok, detail)."""
    res = []
    for f in FILES:
        rp, ep = os.path.join(out_dir, f), os.path.join(expected_dir, f)
        if not os.path.exists(rp):
            res.append((f, False, "run file missing")); continue
        if not os.path.exists(ep):
            res.append((f, False, "golden missing")); continue
        a, b = _norm(rp), _norm(ep)
        if a == b:
            res.append((f, True, ""))
        else:
            # locate first differing line for a helpful message
            al, bl = a.split(b"\n"), b.split(b"\n")
            first = next((k for k in range(min(len(al), len(bl))) if al[k] != bl[k]), None)
            detail = f"len {len(a)}!={len(b)}"
            if first is not None:
                detail += f" · first diff line {first}: run={al[first][:80]!r} exp={bl[first][:80]!r}"
            res.append((f, False, detail))
    return res


def _run_one(strategy_cls, config_stem: str, out_dir: str) -> int:
    """Inject strategy_cls into the snapshot registry and run `bt run` in-process."""
    import bt.strategies.registry as _reg
    from bt import __main__ as bt_main
    _reg.STRATEGIES[strategy_cls.name] = strategy_cls   # mutate shared dict (engine duck-types)
    cfg_path = os.path.join(SNAP, "configs", config_stem + ".yaml")
    argv = ["run", "--strategy", strategy_cls.name, "--config", cfg_path,
            "--global", GLOBAL, "--data", DATA, "--out", out_dir]
    return bt_main.main(argv)


def main() -> int:
    selfcheck = "--selfcheck" in sys.argv
    if selfcheck:
        from bt.strategies.mountain_v3 import MountainV3 as Core
        label = "SNAPSHOT MountainV3 (self-check)"
    else:
        try:
            from strategies.mountain_v3_core import MountainV3 as Core   # repo ported core
        except (ImportError, AttributeError) as e:
            print("=" * 64)
            print("  Mountain v3 PARITY — repo core NOT available yet")
            print(f"  strategies.mountain.MountainV3 import failed: {e}")
            print("  (expected during Phase 1 — RED baseline)")
            print("=" * 64)
            print("  RESULT: FAIL")
            return 1
        label = "REPO strategies.mountain.MountainV3"

    print("=" * 64)
    print(f"  Mountain v3 — BYTE-IDENTICAL PARITY  ·  {label}")
    print("=" * 64)
    all_ok = True
    for stem, exp in CONFIGS:
        out_dir = tempfile.mkdtemp(prefix=f"mtnv3_{stem}_")
        try:
            rc = _run_one(Core, stem, out_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{stem}] engine raised {type(exc).__name__}: {exc}")
            all_ok = False
            continue
        res = _diff_run(out_dir, os.path.join(SNAP, "expected_results", exp))
        ok = rc == 0 and all(r[1] for r in res)
        all_ok = all_ok and ok
        print(f"  [{stem}]  {'IDENTICAL' if ok else 'MISMATCH'}  (exit={rc})")
        for f, fok, detail in res:
            mark = "ok" if fok else "FAIL"
            print(f"      [{mark}] {f}" + (f"  — {detail}" if detail else ""))
    print("=" * 64)
    print("  golden: tpsl 194/62.37%/+21745.8/->5675.77 · rr85 181/66.30%/+19953.9/->5280.46")
    print("=" * 64)
    print("  RESULT: PASS" if all_ok else "  RESULT: FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
