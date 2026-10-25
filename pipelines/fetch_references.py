"""Reference sources that fix model parameters and benchmarks.

- FAO AGS Bulletin 152 §3.2 (Kader & Rolle 2004): Table 1 temperature → relative deterioration velocity.
  Parsed from the fetched HTML → data/processed/fao152_table1.csv (REAL_FETCHED).
- NABCONS 2022 via PIB release 2151371, Annexure-II Tables 1–2 → data/processed/benchmarks_nabcons.csv.
- USDA ARS Agriculture Handbook 66 (rev. 2016): onion and orange storage lives, located by page and
  matched by exact phrase in the extracted PDF text (fails loudly if the phrase is not found).
- UC Davis PREC Produce Facts: Tomato (Suslow & Cantwell, 1997): **citation only**. The page forbids
  copying/storing its content, so no raw copy is kept; the value and access date are recorded.
"""
from __future__ import annotations

import io
import re
import sys

import pandas as pd
from pypdf import PdfReader

from pipelines.common import (
    PROCESSED,
    RAW,
    AuditRecord,
    SourceMeta,
    fetch_cached,
    manifest_id,
    utcnow,
    write_audit,
    write_csv_deterministic,
)

FAO = SourceMeta("fao_ags_bulletin_152",
                 "UNVERIFIED: FAO copyright. FAO generally permits non-commercial reproduction with acknowledgement; "
                 "only the cited table values are reused here.",
                 "https://www.fao.org/contact-us/terms/en/", "Kader & Rolle (2004) FAO AGS Bulletin 152, ch. 3")
FAO_URL = "https://www.fao.org/4/y5431e/y5431e04.htm"
PIB = SourceMeta("pib_2151371", "Government of India press release (PIB). UNVERIFIED reuse terms; cited with attribution.",
                 "https://www.pib.gov.in/", "NABCONS 2022 study for MoFPI as tabled in Rajya Sabha, 1 Aug 2025")
PIB_URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2151371"
HB66 = SourceMeta("usda_hb66", "US Government work (USDA ARS); UNVERIFIED: public-domain status not confirmed on the hosting page.",
                  "https://ageconsearch.umn.edu/record/348552",
                  "USDA ARS Agriculture Handbook 66, rev. Feb 2016 (Gross, Wang, Saltveit eds.)")
HB66_URL = "https://ageconsearch.umn.edu/record/348552/files/ah66rev.pdf"
UCD_TOMATO_URL = "https://postharvest.ucdavis.edu/produce-facts-sheets/tomato"


def fao_table1(refresh: bool) -> pd.DataFrame:
    p, status = fetch_cached(FAO, "y5431e04.htm", FAO_URL, refresh=refresh)
    if p is None:
        raise RuntimeError(f"FAO 152 page unavailable ({status})")
    html = p.read_text(encoding="utf-8", errors="replace")
    if "two to three-fold with every 10" not in re.sub(r"\s+", " ", html):
        raise RuntimeError("FAO 152: Q10 sentence not found; page changed?")
    t = pd.read_html(io.StringIO(html))[0]
    t.columns = ["temp_c", "assumed_q10", "relative_velocity", "relative_life", "loss_per_day_pct"]
    t = t.iloc[1:].replace("-", None).astype(float).reset_index(drop=True)
    if t["temp_c"].tolist() != [0, 10, 20, 30, 40]:
        raise RuntimeError(f"FAO Table 1 shape changed: {t['temp_c'].tolist()}")
    t["provenance"] = "REAL_FETCHED"
    t["source_manifest_id"] = manifest_id(FAO.source, "y5431e04.htm")
    t["source_detail"] = "FAO AGS Bulletin 152 §3.2 Table 1 (generic non-chilling-sensitive commodity)"
    return t


def nabcons(refresh: bool) -> pd.DataFrame:
    p, status = fetch_cached(PIB, "PRID_2151371.html", PIB_URL, refresh=refresh)
    if p is None:
        raise RuntimeError(f"PIB 2151371 unavailable ({status})")
    html = p.read_text(encoding="utf-8", errors="replace")
    mid = manifest_id(PIB.source, "PRID_2151371.html")
    tables = pd.read_html(io.StringIO(html))
    t2 = next(t for t in tables if t.astype(str).apply(lambda c: c.str.contains("Tomato")).any().any()
              and t.astype(str).apply(lambda c: c.str.contains("Paddy")).any().any())
    t2 = t2.astype(str)
    rows, category = [], None
    for _, r in t2.iterrows():
        vals = [str(v).strip() for v in r.tolist()]
        nums = [v for v in vals if re.fullmatch(r"\d+(\.\d+)?", v)]
        names = [v for v in vals if v and v.lower() != "nan" and not re.fullmatch(r"\d+(\.\d+)?", v)]
        if len(nums) >= 2 and names:
            if len(names) >= 2:
                category = names[0]
            crop = names[-1]
            rows.append({"category": category, "crop": crop, "farm_operations_loss_pct": float(nums[-2]),
                         "market_level_loss_pct": float(nums[-1])})
    df = pd.DataFrame(rows)
    need = {"Tomato": (8.37, 3.25), "Onion": (5.31, 1.96), "Citrus": (5.53, 2.18)}
    for crop, (farm, market) in need.items():
        hit = df[df["crop"] == crop]
        if hit.empty or (hit.iloc[0]["farm_operations_loss_pct"], hit.iloc[0]["market_level_loss_pct"]) != (farm, market):
            raise RuntimeError(f"NABCONS row check failed for {crop}: {hit.to_dict('records')}")
    df["reference_period"] = "2020-22"
    df["caveat"] = ("'Market level' bundles wholesale, retail, processing and transport at market level; "
                    "not a transit-only loss figure. Citrus is a category, not Nagpur orange specifically.")
    df["provenance"] = "REAL_FETCHED"
    df["source_manifest_id"] = mid
    return df


def hb66_values() -> list[dict]:
    p = RAW / HB66.source / "ah66rev.pdf"
    if not p.exists():
        raise RuntimeError("HB66 PDF missing: run fetch_references with network once")
    reader = PdfReader(str(p))
    mid = manifest_id(HB66.source, "ah66rev.pdf")

    def find(phrase: str, pages: range) -> int:
        for i in pages:
            if phrase in re.sub(r"\s+", " ", reader.pages[i].extract_text() or ""):
                return i + 1
        raise RuntimeError(f"HB66 phrase not found: {phrase!r}")

    onion_pg = find("Pungent dry onions can be stored for 6 to 9 mo at 0 °C", range(440, 455))
    orange_pg = find("Oranges can be stored for up to 12 weeks under optimum storage conditions", range(445, 460))
    return [
        {"commodity": "onion", "life_h": 6 * 730.0, "ref_temp_c": 0.0,
         "statement": "Pungent dry onions: 6 to 9 months at 0 °C, 65–75% RH",
         "choice": "lower bound (6 months = 4380 h; 1 month = 730 h)",
         "source": f"USDA ARS Agriculture Handbook 66 (rev. 2016), 'Onion' (Adamicki), PDF page {onion_pg}",
         "source_manifest_id": mid},
        {"commodity": "orange", "life_h": 12 * 168.0, "ref_temp_c": 1.0,
         "statement": "Oranges: up to 12 weeks under optimum storage (FL & TX: 0–1 °C, 85–90% RH)",
         "choice": "stated maximum ('up to'): no lower bound is given, so this is OPTIMISTIC; temperature = upper end of 0–1 °C",
         "source": f"USDA ARS Agriculture Handbook 66 (rev. 2016), 'Orange', PDF page {orange_pg}",
         "source_manifest_id": mid},
    ]


def ucd_tomato_citation() -> dict:
    """Citation-only record (no raw copy: the page forbids storing its content)."""
    return {"commodity": "tomato", "life_h": 8 * 24.0, "ref_temp_c": 10.0,
            "statement": "Typically 8–10 days of shelf life within the optimum range (firm-ripe: 7–10 °C)",
            "choice": "lower bound of life (8 d) at the upper end of the optimum range (10 °C), "
                      "since the life is stated as attainable within that range",
            "source": "Suslow, T.V. & Cantwell, M. (1997, last updated May 1997). Produce Fact Sheet: Tomato. UC Davis "
                      f"Postharvest Research and Extension Center. {UCD_TOMATO_URL} (accessed 2026-10-24, read in browser)",
            "source_manifest_id": "citation_only:ucdavis_prec_tomato_2026-10-24"}


def run(refresh: bool = False) -> None:
    fetch_cached(HB66, "ah66rev.pdf", HB66_URL, refresh=refresh, min_interval_s=2)
    t1 = fao_table1(refresh)
    write_csv_deterministic(t1, PROCESSED / "fao152_table1.csv", ["temp_c"])
    nb = nabcons(refresh)
    write_csv_deterministic(nb, PROCESSED / "benchmarks_nabcons.csv", ["category", "crop"])
    lives = pd.DataFrame(hb66_values() + [ucd_tomato_citation()])
    lives["provenance"] = "REAL_FETCHED"
    lives["recorded_at_utc"] = utcnow()[:10]
    lives["warning"] = ("Reference life at a cold/optimal temperature. Extrapolation to ambient transit temperatures uses "
                        "FAO Table 1 and is an ASSUMPTION; crop-specific rates differ (FAO 152).")
    write_csv_deterministic(lives.drop(columns=["recorded_at_utc"]), PROCESSED / "crop_shelf_life_refs.csv", ["commodity"])

    write_audit("crop_profiles", AuditRecord(
        need="Crop profiles: reference shelf life, temperature sensitivity (decay model M3/simulation)",
        source_name="FAO AGS Bulletin 152; USDA ARS Agriculture Handbook 66 (2016); UC Davis PREC Produce Facts (tomato)",
        status="PARTIAL", access="HTTP GET (FAO HTML, HB66 PDF); browser read (UC Davis, citation only)", auth="none",
        licence="FAO: see page terms; HB66: US Gov work (UNVERIFIED); UC Davis: personal/educational use only, no copying, "
                "commercial use forbidden. Values cited, not reproduced.",
        coverage="Temperature curve: FAO Table 1 (0–40 °C). Reference lives: tomato 8 d @10 °C (UC Davis), "
                 "onion 6 mo @0 °C (HB66), orange 12 wk @1 °C (HB66, 'up to' → optimistic).",
        tried=[f"GET {FAO_URL}", f"GET {HB66_URL}", f"Browser read {UCD_TOMATO_URL} (WebFetch returned 403)",
               "ICAR/KVK crop profiles: not searched systematically; no machine-readable source identified"],
        why_failed="No source gives ambient (25–40 °C) transit shelf life for these crops in Indian conditions; "
                   "harvest-maturity profiles from ICAR/KVK not located.",
        fallback="Reference life × FAO Table 1 relative velocity (log-linear interpolation); Q10=2 and Q10=3 run as "
                 "sensitivity bounds. Every decay output carries the extrapolation warning.",
        urls=[FAO_URL, HB66_URL, UCD_TOMATO_URL],
        known_problems="Cold-storage reference lives extrapolated over 25–40 °C; Nagpur orange cultivar not specifically "
                       "covered (HB66 'Orange' is US-grown sweet orange); tomato value is from a 1997 fact sheet.",
        flags=["EXTRAPOLATION_ASSUMPTION", "UCDAVIS_NO_COPY", "ORANGE_VALUE_OPTIMISTIC"]))
    write_audit("loss_benchmarks", AuditRecord(
        need="Loss benchmarks for calibration/plausibility and the Evidence page",
        source_name="NABCONS 2022 for MoFPI, via PIB release 2151371 (Annexure-II)",
        status="AVAILABLE", access="HTTP GET HTML; tables parsed by code", auth="none", licence=PIB.licence,
        coverage=f"{len(nb)} crop rows; tomato 3.25%, onion 1.96%, citrus 2.18% market-level (checked by assertion)",
        tried=[f"GET {PIB_URL}"], urls=[PIB_URL],
        known_problems="Market level ≠ transit loss. 'Citrus' ≠ Nagpur orange. National, not Nagpur-specific. "
                       "WRI India 2024, RBI WPS 08/2024, NCCD 2015 are cited in the brief but not fetched here.",
        flags=["PLAUSIBILITY_ONLY"]))
    print(f"references: FAO table {len(t1)} rows; NABCONS {len(nb)} rows; shelf-life refs {len(lives)}")
    print(lives[["commodity", "life_h", "ref_temp_c", "choice"]].to_string(index=False))


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
