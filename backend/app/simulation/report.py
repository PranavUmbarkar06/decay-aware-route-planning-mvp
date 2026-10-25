"""reports/simulation_report.html: evaluation report generated from reports/sim/*/{runs,paired}.csv + summary.json.

Every number is labelled "Simulation output, not field-validated". No target reduction is stated.
Charts: matplotlib PNG (embedded) with legend + a table view of the same numbers.
"""
from __future__ import annotations

import base64
import html
import io
import json
import subprocess
from datetime import UTC, datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from app.core.config import ROOT  # noqa: E402

SIM = ROOT / "reports" / "sim"
OUT = ROOT / "reports" / "simulation_report.html"
BLUE, ORANGE = "#2a78d6", "#eb6834"          # reference palette slots 1–2 (validated adjacent pair)
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
LABEL = "Simulation output, not field-validated"
POL = {"StaticShortestPath": "Baseline: static shortest path", "QualityAwareDynamic": "Proposed: quality-aware dynamic",
       "QualityAwareDynamic+diurnal": "Proposed + diurnal forecast"}


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def seeds_chart(runs: pd.DataFrame, metric: str, title: str) -> str:
    seasons = list(dict.fromkeys(runs["season"]))
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    for i, s in enumerate(seasons):
        for j, (pol, col) in enumerate((("StaticShortestPath", BLUE), (None, ORANGE))):
            g = runs[(runs["season"] == s) & ((runs["policy"] == pol) if pol else (runs["policy"] != "StaticShortestPath"))]
            x = i + (-0.16 if j == 0 else 0.16)
            ax.scatter([x] * len(g), g[metric] * 100, s=22, color=col, alpha=0.75, edgecolor="white", linewidth=0.6,
                       label=(POL["StaticShortestPath"] if j == 0 else POL["QualityAwareDynamic"]) if i == 0 else None, zorder=3)
            ax.hlines(g[metric].mean() * 100, x - 0.11, x + 0.11, color=col, linewidth=2.2, zorder=4)
    ax.set_xticks(range(len(seasons)), [s.capitalize() for s in seasons])
    ax.set_ylabel("%", color=MUTED)
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", bbox_to_anchor=(0, -0.12), ncol=2)
    _style(ax)
    fig.text(0.99, 0.01, LABEL, ha="right", fontsize=7.5, color=MUTED)
    return _png(fig)


def diff_chart(runs: pd.DataFrame, metric: str, title: str) -> str:
    seasons = list(dict.fromkeys(runs["season"]))
    fig, axes = plt.subplots(1, len(seasons), figsize=(7.5, 2.6), sharey=True)
    for ax, s in zip(axes, seasons, strict=True):
        b = runs[(runs["season"] == s) & (runs["policy"] == "StaticShortestPath")].set_index("seed")[metric]
        p = runs[(runs["season"] == s) & (runs["policy"] != "StaticShortestPath")].set_index("seed")[metric]
        d = ((p - b) * 100).sort_index()
        cols = [ORANGE if v > 0 else BLUE for v in d]
        ax.bar(range(len(d)), d.values, color=cols, width=0.7)
        ax.axhline(0, color=MUTED, linewidth=0.8)
        ax.set_title(s.capitalize(), fontsize=9.5, color=INK)
        ax.set_xticks([])
        _style(ax)
    axes[0].set_ylabel("proposed − baseline (pp)", color=MUTED, fontsize=8.5)
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, color=INK)
    fig.text(0.01, -0.04, "Each bar = one seed. Above 0 (orange) = proposed worse; below 0 (blue) = proposed better.",
             fontsize=8, color=MUTED)
    fig.text(0.99, -0.04, LABEL, ha="right", fontsize=7.5, color=MUTED)
    return _png(fig)


def _fmt(v, pct=False, nd=2):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    return f"{v * 100:.{nd}f}%" if pct else f"{v:,.{nd}f}"


def results_table(pr: pd.DataFrame) -> str:
    pct = {"wastage_rate", "unmet_demand_rate", "mean_quality_at_sink"}
    rows = []
    for r in pr.itertuples(index=False):
        p = r.metric in pct
        unit = "pp" if p else ""
        verdict = "better" if r.proposed_better else ("worse" if r.proposed_worse else "no clear difference")
        rows.append(f"<tr><td>{r.season}</td><td>{r.metric}</td><td>{_fmt(r.baseline_mean, p)} ± {_fmt(r.baseline_sd, p)}</td>"
                    f"<td>{_fmt(r.proposed_mean, p)} ± {_fmt(r.proposed_sd, p)}</td>"
                    f"<td>{_fmt(r.mean_diff * (100 if p else 1), False)}{unit} "
                    f"[{_fmt(r.ci95_lo * (100 if p else 1), False)}, {_fmt(r.ci95_hi * (100 if p else 1), False)}]</td>"
                    f"<td>{verdict}</td><td>{r.seeds_proposed_worse}/{r.n_seeds}</td></tr>")
    return ("<table><thead><tr><th>Season</th><th>Metric</th><th>Baseline mean ± sd</th><th>Proposed mean ± sd</th>"
            "<th>Paired diff [95% bootstrap CI]</th><th>Proposed is…</th><th>Seeds where proposed worse</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def calibration(runs: pd.DataFrame, cfg: dict) -> str:
    nab = cfg["calibration_check"]["nabcons_pct"]
    f = cfg["calibration_check"]["flag_if_outside_factor"]
    b = runs[runs["policy"] == "StaticShortestPath"]
    rows = []
    for c, key in (("tomato", "tomato"), ("onion", "onion"), ("orange", "orange_citrus")):
        rates = [json.loads(x)[c]["wastage_rate"] for x in b["per_commodity"] if json.loads(x)[c]["wastage_rate"] is not None]
        if not rates:
            rows.append(f"<tr><td>{c}</td><td>no lots in these seasons</td><td>{nab[key]}%</td><td>–</td><td>–</td></tr>")
            continue
        sim = sum(rates) / len(rates) * 100
        ratio = sim / nab[key]
        flag = "FLAG: outside plausibility band" if (ratio > f or ratio < 1 / f) else "within band"
        rows.append(f"<tr><td>{c}</td><td>{sim:.2f}% (n={len(rates)} runs)</td><td>{nab[key]}%</td><td>{ratio:.1f}×</td><td>{flag}</td></tr>")
    return ("<table><thead><tr><th>Commodity</th><th>Simulated baseline wastage (mean)</th><th>NABCONS market-level loss</th>"
            "<th>Ratio</th><th>Plausibility (±" + str(f) + "×)</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
            "<p class='note'>Plausibility only. NABCONS 'market level' bundles wholesale, retail, processing and transport; it is "
            "<b>not</b> a transit-loss figure, and 'Citrus' is not Nagpur orange specifically. A flag means the model's assumptions "
            "(cold-storage reference lives extrapolated to ambient heat, A2/A3/A17) need field data; it is reported, not tuned away.</p>")


def _set(name: str) -> tuple[pd.DataFrame, pd.DataFrame, dict] | None:
    d = SIM / name
    if not (d / "runs.csv").exists():
        return None
    return pd.read_csv(d / "runs.csv"), pd.read_csv(d / "paired.csv"), json.loads((d / "summary.json").read_text(encoding="utf-8"))


def verdict_block(summary: dict) -> str:
    items = []
    for v in summary["verdicts"]:
        word = "beats the baseline on both primary metrics" if v["beats_baseline"] else "does NOT beat the baseline"
        g = " · guardrail flag: travel time or km up >10%" if v["guardrail_flag"] else ""
        fails = ", ".join(map(str, v["failure_seeds"])) or "none"
        items.append(f"<li><b>{html.escape(v['variant'])} / {v['season']}</b>: proposed {word}{g}. "
                     f"Seeds where proposed is worse on a primary metric ({v['n_failures']}): {fails}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def write_report() -> str:
    cfg = yaml.safe_load((ROOT / "config" / "experiments.yaml").read_text(encoding="utf-8"))
    code_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    prim = _set("primary")
    if prim is None:
        raise SystemExit("no primary results: run `python tasks.py experiments --set primary` first")
    runs, pr, summ = prim
    sections = []
    sections.append(f"""<h2>1. Pre-registered result</h2>
<p class="note">Design, metrics and decision rule were committed before any run: <code>{html.escape(summ['preregistration_commit'])}</code>
(SHA-256 <code>{summ['preregistration_sha256'][:16]}…</code>). Seeds {summ['seeds'][0]}–{summ['seeds'][-1]} × seasons
{', '.join(cfg['seasons'])} × 2 policies. Decision rule: proposed "beats baseline" in a season only if the 95% paired bootstrap CI
is entirely below 0 for <b>both</b> wastage rate and unmet-demand rate.</p>
{verdict_block(summ)}
<img alt="Wastage rate by season and seed" src="{seeds_chart(runs, 'wastage_rate', 'Wastage rate per run (dots) and mean (bar)')}">
<img alt="Unmet demand rate by season and seed" src="{seeds_chart(runs, 'unmet_demand_rate', 'Unmet-demand rate per run (dots) and mean (bar)')}">
<img alt="Paired difference in wastage rate per seed" src="{diff_chart(runs, 'wastage_rate', 'Paired difference in wastage rate, per seed')}">
<h3>Table view (all pre-registered metrics)</h3>{results_table(pr)}
<p class="note">Mass balance (injected = sold + donated + processed + wasted + in market + in transit) was asserted on every tick of every
run; largest absolute error: {summ['max_abs_balance_error_kg']:.2e} kg.</p>""")
    sections.append(f"<h2>2. Plausibility check against NABCONS</h2>{calibration(runs, cfg)}")
    agg = runs.groupby(["season", "policy"])[["injected_kg", "sold_kg", "donated_kg", "processed_kg", "wasted_heat_kg",
                                              "wasted_crushed_kg", "wasted_unsold_kg", "reroute_count", "redirect_count"]].mean()
    sections.append("<h2>3. Where the produce went (mean per run, kg)</h2>"
                    + agg.round(0).reset_index().to_html(index=False, border=0)
                    + "<p class='note'>DONATED and PROCESSED are not counted as wastage. CRUSHED uses the placeholder handling rate "
                      "(A6); HEAT_ROT comes from the decay model; UNSOLD = expired at market or beyond NGO capacity.</p>")
    sens = _set("sensitivity")
    if sens:
        s_runs, s_pr, s_sum = sens
        t = s_pr[s_pr["metric"].isin(["wastage_rate", "unmet_demand_rate"])][
            ["variant", "season", "metric", "baseline_mean", "proposed_mean", "mean_diff", "ci95_lo", "ci95_hi"]]
        sections.append("<h2>4. Pre-registered sensitivity runs (exploratory, seeds "
                        f"{s_sum['seeds'][0]}–{s_sum['seeds'][-1]})</h2>" + t.round(4).to_html(index=False, border=0)
                        + verdict_block(s_sum))
    exp = _set("exploratory")
    if exp:
        e_runs, e_pr, e_sum = exp
        t = e_pr[e_pr["metric"].isin(["wastage_rate", "unmet_demand_rate"])][
            ["variant", "season", "metric", "baseline_mean", "proposed_mean", "mean_diff", "ci95_lo", "ci95_hi"]]
        sections.append("<h2>5. EXPLORATORY_POSTHOC variants (not part of the decision rule)</h2>"
                        "<p class='warn'>Added after engineering runs showed two design properties that favour the baseline "
                        "(ADR-023). These results generate hypotheses only; they must be re-registered before being used as evidence.</p>"
                        + t.round(4).to_html(index=False, border=0) + verdict_block(e_sum))
    sections.append("""<h2>6. What this does and does not show</h2><ul>
<li>Supply lots are SYNTHETIC (seeded); roads (OSM), weather (Open-Meteo replay) and daily market volumes (Agmarknet exports) are real.</li>
<li>Congestion and disruptions are modelled (ASSUMPTION A9), never observed traffic.</li>
<li>Decay uses cold-storage reference lives extrapolated with FAO's generic temperature curve (A2, A3, A17); the plausibility check
above shows how far the absolute levels may be off. Comparisons between policies are more robust than absolute levels, but both
depend on these assumptions.</li>
<li>Planned destinations follow the day's realised arrivals (A24), which gives the baseline implicit demand knowledge.</li>
<li>Dispatcher needs have not been validated by interviews. The system recommends; humans decide.</li>
<li>No percentage reduction is claimed or targeted. The deck's 14% figure is provisional and unsourced and is not used.</li></ul>""")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Simulation report</title><style>
:root{{--bg:#fcfcfb;--fg:#0b0b0b;--muted:#52514e;--line:#e4e3df;--warn:#b9472e}}
body{{margin:0 auto;padding:16px;max-width:980px;font:15px/1.55 system-ui,sans-serif;background:var(--bg);color:var(--fg)}}
h1{{font-size:24px}} h2{{font-size:18px;margin-top:32px;border-bottom:1px solid var(--line);padding-bottom:4px}}
table{{border-collapse:collapse;font-size:12.5px;display:block;overflow-x:auto;margin:8px 0}} td,th{{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left}}
img{{max-width:100%;display:block;margin:12px 0}} .note{{color:var(--muted);font-size:13px}} .warn{{color:var(--warn);font-weight:600}}
.banner{{background:#fff4e5;border:1px solid #eda100;padding:10px 12px;border-radius:6px}}</style></head><body>
<div class="banner"><b>{LABEL}.</b> Synthetic supply on real roads, weather and market volumes. Not a measurement of real loss.</div>
<h1>Quality-aware routing vs static baseline: simulation report</h1>
<p class="note">Generated {datetime.now(UTC).isoformat(timespec='seconds')} from code commit <code>{code_commit[:10]}</code>.
Configs: <code>config/simulation.yaml</code>, <code>config/experiments.yaml</code>. Raw per-run logs: <code>reports/sim/</code>.</p>
{''.join(sections)}</body></html>"""
    OUT.write_text(page, encoding="utf-8")
    return str(OUT)
