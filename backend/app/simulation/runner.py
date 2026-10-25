"""`python tasks.py experiments [--set primary|sensitivity|exploratory|all] [--workers N]` and `python tasks.py report`.

Primary set = exactly the pre-registered design (config/experiments.yaml). The runner refuses to run if that file
has uncommitted changes, and records its commit + SHA-256 with every run. Sensitivity runs are those listed in the
pre-registration (exploratory). Post-hoc variants are labelled EXPLORATORY_POSTHOC and never enter the decision rule.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import yaml

from app.core.config import ROOT

OUT = ROOT / "reports" / "sim"
EXP = ROOT / "config" / "experiments.yaml"
POLICIES = ["StaticShortestPath", "QualityAwareDynamic"]

POSTHOC_VARIANTS = [   # logged as deviations; see docs/DECISIONS.md ADR-023
    {"name": "posthoc_plan_from_forecast", "scenario": {"plan_from_forecast": True}, "policy_kw": {}},
    {"name": "posthoc_diurnal_forecast", "scenario": {}, "policy_kw": {"diurnal": True}},
    {"name": "posthoc_both", "scenario": {"plan_from_forecast": True}, "policy_kw": {"diurnal": True}},
]


def prereg() -> dict:
    cfg = yaml.safe_load(EXP.read_text(encoding="utf-8"))
    dirty = subprocess.run(["git", "status", "--porcelain", "--", str(EXP)], cwd=ROOT, capture_output=True, text=True).stdout
    commit = subprocess.run(["git", "log", "-1", "--format=%H %cI", "--", str(EXP)], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    return {"cfg": cfg, "dirty": bool(dirty.strip()), "commit": commit,
            "sha256": hashlib.sha256(EXP.read_bytes()).hexdigest()}


# ------------------------------------------------------------------ one run (executed in worker processes)
def _run_one(job: dict) -> dict:
    from app.simulation.engine import Engine
    from app.simulation.network import load_network
    from app.simulation.policies import make_policy
    from app.simulation.scenario import build_scenario

    net = load_network()
    sc = build_scenario(net, job["season"], job["start"], job["days"], job["seed"], job["commodities"],
                        overrides=job.get("scenario") or None)
    eng_kw = {k: job[k] for k in ("decay_mode", "q10", "truck_offset") if k in job}
    pol = make_policy(job["policy"], **(job.get("policy_kw") or {}))
    t0 = time.perf_counter()
    r = Engine(net, sc, pol, record_replay=job.get("replay", False), **eng_kw).run()
    elapsed = time.perf_counter() - t0
    ev = pd.DataFrame(r.events)
    ev_bytes = ev.to_csv(index=False, lineterminator="\n").encode()
    tag = f"{job['set']}__{job['variant']}__{job['season']}__{job['seed']}__{r.policy}"
    d = OUT / job["set"] / "runs"
    d.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(d / f"{tag}__events.csv.gz", "wb", mtime=0) as f:   # mtime=0 → byte-identical reruns
        f.write(ev_bytes)
    pd.DataFrame(r.lots).to_csv(d / f"{tag}__lots.csv", index=False, lineterminator="\n", float_format="%.6f")
    pd.DataFrame(r.balance).to_csv(d / f"{tag}__balance.csv", index=False, lineterminator="\n", float_format="%.6f")
    if r.replay is not None:
        (OUT / f"replay__{job['season']}__{job['seed']}__{r.policy}.json").write_text(
            json.dumps({"season": job["season"], "seed": job["seed"], "policy": r.policy, "start": job["start"],
                        "provenance": "SIMULATION OUTPUT (SYNTHETIC lots on real roads/weather), not field-validated",
                        "fields": ["lot_id", "lat", "lon", "status", "dest", "commodity", "quality"], "ticks": r.replay},
                       separators=(",", ":")), encoding="utf-8")
    return {"set": job["set"], "variant": job["variant"], "season": job["season"], "seed": job["seed"],
            "policy": r.policy, **{k: v for k, v in r.metrics.items()},
            "per_commodity": json.dumps(r.per_commodity), "events_sha256": hashlib.sha256(ev_bytes).hexdigest(),
            "runtime_s": round(elapsed, 2), "scenario_params": json.dumps(sc.params, sort_keys=True),
            "notes": " || ".join(r.notes)}


def jobs_for(set_name: str, cfg: dict, seeds: list[int]) -> list[dict]:
    jobs = []
    seasons = cfg["seasons"]
    base = {"days": None, "commodities": cfg["commodities"]}
    if set_name == "primary":
        variants = [{"name": "registered", "scenario": {}, "policy_kw": {}}]
    elif set_name == "sensitivity":
        variants = []
        for s in cfg["sensitivity_exploratory"]:
            v = {"name": s["name"], "scenario": {}, "policy_kw": {}}
            if "decay_mode" in s:
                v["decay_mode"], v["q10"] = s["decay_mode"], s["q10"]
            if "truck_temp_offset_c" in s:
                v["truck_offset"] = s["truck_temp_offset_c"]
            if "supply_ratio" in s:
                v["scenario"] = {"supply_ratio": s["supply_ratio"]}
            variants.append(v)
    else:
        variants = POSTHOC_VARIANTS
    for v in variants:
        for season, sv in seasons.items():
            for seed in seeds:
                for pol in POLICIES:
                    j = {**base, "set": set_name, "variant": v["name"], "season": season, "start": sv["start"],
                         "days": sv["days"], "seed": seed, "policy": pol, "scenario": v.get("scenario"),
                         "replay": set_name == "primary" and season == "summer" and seed == seeds[0]}
                    if pol == "QualityAwareDynamic":
                        j["policy_kw"] = v.get("policy_kw")
                    for k in ("decay_mode", "q10", "truck_offset"):
                        if k in v:
                            j[k] = v[k]
                    jobs.append(j)
    return jobs


# ------------------------------------------------------------------ statistics (pre-registered rule)
def paired(runs: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rng = np.random.default_rng(20261025)
    rows = []
    for (st, var, season), g in runs.groupby(["set", "variant", "season"]):
        b = g[g["policy"] == "StaticShortestPath"].set_index("seed")
        p = g[~(g["policy"] == "StaticShortestPath")].set_index("seed")
        seeds = sorted(set(b.index) & set(p.index))
        for metric, lower_better in (("wastage_rate", True), ("unmet_demand_rate", True), ("mean_quality_at_sink", False),
                                     ("mean_travel_h_per_lot", True), ("total_km", True), ("wasted_kg", True)):
            diff = (p.loc[seeds, metric] - b.loc[seeds, metric]).to_numpy(float)
            boots = np.array([np.mean(rng.choice(diff, size=len(diff), replace=True)) for _ in range(10_000)]) if len(diff) else np.array([np.nan])
            lo, hi = np.nanpercentile(boots, [2.5, 97.5])
            better = (hi < 0) if lower_better else (lo > 0)
            worse = (lo > 0) if lower_better else (hi < 0)
            rows.append({"set": st, "variant": var, "season": season, "metric": metric, "n_seeds": len(diff),
                         "baseline_mean": float(b.loc[seeds, metric].mean()), "baseline_sd": float(b.loc[seeds, metric].std()),
                         "proposed_mean": float(p.loc[seeds, metric].mean()), "proposed_sd": float(p.loc[seeds, metric].std()),
                         "mean_diff": float(np.mean(diff)) if len(diff) else np.nan, "ci95_lo": lo, "ci95_hi": hi,
                         "proposed_better": bool(better), "proposed_worse": bool(worse),
                         "seeds_proposed_worse": int(np.sum(diff > 0) if lower_better else np.sum(diff < 0))})
    return pd.DataFrame(rows)


def verdicts(pr: pd.DataFrame, runs: pd.DataFrame) -> list[dict]:
    out = []
    for (st, var, season), g in pr.groupby(["set", "variant", "season"]):
        gm = g.set_index("metric")
        both = bool(gm.loc["wastage_rate", "proposed_better"] and gm.loc["unmet_demand_rate", "proposed_better"])
        travel = gm.loc["mean_travel_h_per_lot"]
        km = gm.loc["total_km"]
        flag = (travel["proposed_mean"] > 1.1 * travel["baseline_mean"]) or (km["proposed_mean"] > 1.1 * km["baseline_mean"])
        r = runs[(runs["set"] == st) & (runs["variant"] == var) & (runs["season"] == season)]
        b = r[r["policy"] == "StaticShortestPath"].set_index("seed")
        p = r[r["policy"] != "StaticShortestPath"].set_index("seed")
        fails = [int(s) for s in sorted(set(b.index) & set(p.index))
                 if p.loc[s, "wastage_rate"] > b.loc[s, "wastage_rate"] or p.loc[s, "unmet_demand_rate"] > b.loc[s, "unmet_demand_rate"]]
        out.append({"set": st, "variant": var, "season": season, "beats_baseline": both, "guardrail_flag": bool(flag),
                    "failure_seeds": fails, "n_failures": len(fails)})
    return out


def run_set(set_name: str, workers: int, seeds: list[int] | None = None) -> pd.DataFrame:
    pr = prereg()
    if pr["dirty"]:
        raise SystemExit("config/experiments.yaml has uncommitted changes: commit (and log a deviation) before running")
    cfg = pr["cfg"]
    seeds = seeds or (cfg["seeds"] if set_name != "sensitivity" else cfg["seeds"][:5])
    jobs = jobs_for(set_name, cfg, seeds)
    print(f"[{set_name}] {len(jobs)} runs on {workers} workers; pre-registration {pr['commit']}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(_run_one, jobs, chunksize=1))
    runs = pd.DataFrame(rows).sort_values(["variant", "season", "seed", "policy"]).reset_index(drop=True)
    d = OUT / set_name
    d.mkdir(parents=True, exist_ok=True)
    runs.to_csv(d / "runs.csv", index=False, lineterminator="\n")
    prs = paired(runs, cfg)
    prs.to_csv(d / "paired.csv", index=False, lineterminator="\n")
    meta = {"set": set_name, "finished_utc": datetime.now(UTC).isoformat(timespec="seconds"), "wall_s": round(time.time() - t0, 1),
            "preregistration_commit": pr["commit"], "preregistration_sha256": pr["sha256"], "seeds": seeds,
            "verdicts": verdicts(prs, runs),
            "label": {"primary": "PRE-REGISTERED", "sensitivity": "PRE-REGISTERED SENSITIVITY (exploratory)",
                      "exploratory": "EXPLORATORY_POSTHOC (not part of the decision rule)"}[set_name],
            "max_abs_balance_error_kg": float(runs["max_abs_balance_error_kg"].max())}
    (d / "summary.json").write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(meta["verdicts"], indent=1), flush=True)
    return runs


def main(argv: list[str]) -> int:
    cmd = argv[0]
    args = argv[1:]
    if cmd == "experiments":
        which = args[args.index("--set") + 1] if "--set" in args else "primary"
        workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 8
        sets = ["primary", "sensitivity", "exploratory"] if which == "all" else [which]
        for s in sets:
            run_set(s, workers)
        return 0
    if cmd == "report":
        from app.simulation.report import write_report
        print(write_report())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
