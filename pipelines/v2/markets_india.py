"""All-India Agmarknet arrivals → market table + daily arrivals, with offline geocoding (plan v2 §3.5).

Inputs : data/raw/agmarknet_manual_exports/{tomato,onion,grapes}_all_india.csv  (HISTORICAL, Agmarknet)
         data/raw/geoboundaries_ind/*_simplified.geojson                        (district/state polygons)
         OSM place nodes from the India extract (cached to data/cache/india_places.parquet)
Outputs: data/processed/india/markets.parquet, arrivals_daily.parquet, districts.geojson, states.geojson,
         markets_report.json

Geocoding never invents precision: each market records geocode_method and confidence. Markets that only resolve
to their district get the district centroid and method 'district_centroid' (shown as approximate in the UI).
Arrival quantity is NOT demand; see platform_api for how the market load index is derived.

    python -m pipelines.v2.markets_india [path/to/extract.osm.pbf]
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmium
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "agmarknet_manual_exports"
GB = ROOT / "data" / "raw" / "geoboundaries_ind"
PBF = ROOT / "data" / "raw" / "geofabrik_india" / "india-latest.osm.pbf"
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "data" / "processed" / "india"
CROPS = ["tomato", "onion", "grapes"]

STATE_ALIAS = {"andaman and nicobar": "andamanandnicobarislands", "chattisgarh": "chhattisgarh", "keralam": "kerala",
               "nct of delhi": "delhi"}
# Agmarknet uses current/renamed district names; geoBoundaries ADM2 is 2021. ASSUMPTION: new districts map to
# the 2021 parent district that contains their main market town.
DISTRICT_ALIAS = {
    "annamayya": "chittoor", "ysrkadapa": "ysr", "chhapra": "saran", "eastchamparanmotihari": "purbachamparan",
    "luckeesarai": "lakhisarai", "khairagarhchhuikhadangandai": "rajnandgaon", "dahod": "dohad", "sirmore": "sirmaur",
    "belagavi": "belgaum", "bengaluru": "bangalore", "bengalurusouth": "ramanagara", "kalaburagi": "gulbarga",
    "mysuru": "mysore", "vijayanagara": "bellary", "vijayapura": "bijapur", "maihar": "satna", "mauganj": "rewa",
    "narmadapuram": "hoshangabad", "beed": "bid", "chattrapatisambhajinagar": "aurangabad", "dharashiv": "osmanabad",
    "nongpohrbhoi": "ribhoi", "tsemenyu": "kohima", "balasore": "baleshwar", "sonepur": "subarnapur",
    "mohali": "sahibzadaajitsinghnagar", "nawanshahr": "shahidbhagatsinghnagar", "balotra": "barmer", "beawar": "ajmer",
    "kotputlibehror": "jaipur", "hanumakonda": "warangal", "westdistrict": "westtripura", "amroha": "jyotibaphulenagar",
    "ayodhya": "faizabad", "bhadohisantravinagar": "santravidasnagar", "hathras": "mahamayanagar", "kasganj": "kanshiramnagar",
    "khirilakhimpur": "kheri", "lakhimpur": "kheri", "maumaunathbhanjan": "mau", "coochbehar": "kochbihar",
    "hooghly": "hugli", "howrah": "haora", "north24parganas": "northtwentyfourparganas", "sounth24parganas": "southtwentyfourparganas",
}
PLACE_RANK = {"city": 0.85, "town": 0.8, "suburb": 0.7, "neighbourhood": 0.62, "quarter": 0.62, "village": 0.6, "hamlet": 0.45}
URBAN = {"city", "town", "suburb", "neighbourhood", "quarter"}


def norm(s: str | None) -> str:
    if not s or (isinstance(s, float) and np.isnan(s)):
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def skeleton(s: str | None) -> str:
    """Transliteration-tolerant key (w→v, ao/au→av, drop h and vowels, collapse repeats)."""
    n = norm(s).replace("w", "v").replace("ao", "av").replace("au", "av").replace("h", "")
    n = re.sub(r"[aeiouy]", "", n)
    return re.sub(r"(.)\1+", r"\1", n)


NOISE = r"\b(apmc|a\.p\.m\.c|market|mandi|yard|sub ?yard|vegetable|veg|fruits?|f ?& ?v|ff ?& ?v|grain|krishi upaj|" \
        r"mandi samiti|regulated|rmc|uzhavar sandhai|uzhavar|santhe|mkt|new|old|main|wholesale|retail|hat|haat)\b"


def town_tokens(market: str) -> list[str]:
    """Candidate town names from an Agmarknet market label, most specific first."""
    n = re.sub(r"\s+", " ", market).strip()
    out = []
    inner = re.findall(r"\(([^)]+)\)", n)
    outer = re.sub(r"\([^)]*\)", " ", n)
    for part in [outer] + inner:
        p = re.sub(NOISE, " ", part, flags=re.I)
        p = re.sub(r"[^A-Za-z ]", " ", p)
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            out.append(p)
            words = p.split()
            if len(words) > 1:
                out.extend(w for w in words if len(w) > 3)
    seen, res = set(), []
    for t in out:
        k = norm(t)
        if k and k not in seen:
            seen.add(k)
            res.append(t)
    return res


def load_arrivals() -> pd.DataFrame:
    frames = []
    for crop in CROPS:
        d = pd.read_csv(SRC / f"{crop}_all_india.csv", skiprows=1, thousands=",", low_memory=False)
        d = d.rename(columns={"State/UT": "state", "District": "district", "Market": "market", "Modal Price": "modal",
                              "Arrival Quantity": "arrival_t", "Arrival Date": "date", "Min Price": "min_p", "Max Price": "max_p"})
        d["crop"] = crop
        frames.append(d[["state", "district", "market", "crop", "date", "arrival_t", "modal", "min_p", "max_p", "Variety", "Grade"]])
    a = pd.concat(frames, ignore_index=True)
    for c in ("state", "district", "market"):
        a[c] = a[c].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    a["date"] = pd.to_datetime(a["date"], format="%d-%m-%Y")
    n0 = len(a)
    a = a.drop_duplicates()
    print(f"arrivals: {n0:,} rows, {n0 - len(a):,} exact duplicates dropped")
    return a


def aggregate(a: pd.DataFrame) -> pd.DataFrame:
    a = a.assign(pxw=a.modal * a.arrival_t.clip(lower=0.01))
    g = a.groupby(["state", "district", "market", "crop", "date"], as_index=False).agg(
        arrival_t=("arrival_t", "sum"), pxw=("pxw", "sum"), w=("arrival_t", lambda s: s.clip(lower=0.01).sum()),
        rows=("modal", "size"))
    g["modal_rs_q"] = (g.pxw / g.w).round(0)
    return g.drop(columns=["pxw", "w"])


def places_from_pbf(pbf: Path) -> pd.DataFrame:
    cache = CACHE / f"{pbf.name.split('.')[0]}_places.parquet"
    if cache.exists() and cache.stat().st_mtime > pbf.stat().st_mtime:
        return pd.read_parquet(cache)
    flt = osmium.filter.TagFilter(*[("place", p) for p in PLACE_RANK])
    rows = []
    for n in osmium.FileProcessor(str(pbf), osmium.osm.NODE).with_filter(flt):
        name = n.tags.get("name")
        if not name:
            continue
        rows.append((n.id, n.tags.get("place"), name, n.tags.get("name:en"), n.location.lon, n.location.lat))
    df = pd.DataFrame(rows, columns=["osm_id", "place", "name", "name_en", "lon", "lat"])
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    print(f"places: {len(df):,} named place nodes from {pbf.name}")
    return df


def boundaries() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    s = gpd.read_file(GB / "geoBoundaries-IND-ADM1_simplified.geojson")[["shapeName", "geometry"]].rename(columns={"shapeName": "state_name"})
    d = gpd.read_file(GB / "geoBoundaries-IND-ADM2_simplified.geojson")[["shapeName", "shapeID", "geometry"]].rename(columns={"shapeName": "district_name"})
    s["state_key"] = s.state_name.map(norm)
    pts = d.copy()
    pts["geometry"] = d.geometry.representative_point()
    j = gpd.sjoin(pts, s[["state_key", "state_name", "geometry"]], predicate="within", how="left")
    j = j[~j.index.duplicated()]
    d["state_key"] = j.state_key.reindex(d.index).values
    d["state_name"] = j.state_name.reindex(d.index).values
    d["district_key"] = d.district_name.map(norm)
    c = d.geometry.representative_point()
    d["c_lon"], d["c_lat"] = c.x, c.y
    return s, d


def state_key(agm_state: str) -> str:
    k = agm_state.lower().strip()
    return STATE_ALIAS.get(k, norm(k))


def match_district(state: str, district: str, d: gpd.GeoDataFrame) -> int | None:
    sk = state_key(state)
    sub = d[d.state_key == sk]
    if sub.empty:
        sub = d
    dk = norm(re.sub(r"\d+", lambda m: {"24": "twentyfour"}.get(m.group(0), m.group(0)), district))
    dk = DISTRICT_ALIAS.get(norm(district), dk)
    exact = sub.index[sub.district_key == dk]
    if len(exact):
        return int(exact[0])
    keys = sub.district_key.tolist()
    close = difflib.get_close_matches(dk, keys, n=1, cutoff=0.75)
    if close:
        return int(sub.index[sub.district_key == close[0]][0])
    contains = sub.index[sub.district_key.map(lambda k: bool(dk) and (dk in k or k in dk) and min(len(k), len(dk)) >= 4)]
    return int(contains[0]) if len(contains) else None


def geocode(markets: pd.DataFrame, places: pd.DataFrame, dist: gpd.GeoDataFrame) -> pd.DataFrame:
    gp = gpd.GeoDataFrame(places, geometry=gpd.points_from_xy(places.lon, places.lat), crs=4326)
    gp = gpd.sjoin(gp, dist[["geometry"]].assign(didx=dist.index), predicate="within", how="inner")
    gp["k1"] = gp.name.map(norm)
    gp["k2"] = gp.name_en.map(norm)
    by_d = {k: v for k, v in gp.groupby("didx")}
    res = []
    for m in markets.itertuples(index=False):
        di = match_district(m.state, m.district, dist)
        row = {"district_idx": di, "lon": None, "lat": None, "geocode_method": "unresolved", "geocode_confidence": 0.0,
               "geocode_note": ""}
        state_wide = di is None
        if state_wide:
            idxs = dist.index[dist.state_key == state_key(m.state)]
            parts = [by_d[i] for i in idxs if i in by_d]
            sub = pd.concat(parts) if parts else None
        else:
            sub = by_d.get(di)
        hit = None
        if sub is not None:
            for tok in town_tokens(m.market):
                tk = norm(tok)
                if len(tk) < 3:
                    continue
                cand = sub[(sub.k1 == tk) | (sub.k2 == tk)]
                how = "exact"
                if cand.empty:
                    names = sorted((set(sub.k1) | set(sub.k2)) - {""})
                    close = difflib.get_close_matches(tk, names, n=1, cutoff=0.88)
                    if close:
                        cand = sub[(sub.k1 == close[0]) | (sub.k2 == close[0])]
                        how = "fuzzy"
                if cand.empty and len(tk) >= 5:
                    sk = skeleton(tok)
                    cand = sub[(sub.k1.map(skeleton) == sk) & sub.place.isin(["city", "town"])]
                    how = "skeleton"
                if len(cand) and how == "exact" and not cand.place.isin(URBAN).any():
                    # An exact village name can shadow the real market town spelled slightly differently
                    # (Madanapalli village vs Madanapalle town): prefer a close urban match if one exists.
                    urban = sub[sub.place.isin(["city", "town"])]
                    names = sorted((set(urban.k1) | set(urban.k2)) - {""})
                    close = difflib.get_close_matches(tk, names, n=1, cutoff=0.82)
                    if close:
                        cand = urban[(urban.k1 == close[0]) | (urban.k2 == close[0])]
                        how = "fuzzy"
                if len(cand):
                    best = cand.sort_values("place", key=lambda s: s.map(lambda p: -PLACE_RANK.get(p, 0))).iloc[0]
                    conf = PLACE_RANK.get(best.place, 0.4) - {"exact": 0, "fuzzy": 0.1, "skeleton": 0.25}[how]
                    if (cand.place == best.place).sum() > 1:
                        conf -= 0.15
                    if state_wide:
                        conf -= 0.15
                    hit = (best, how, tok, round(conf, 2))
                    break
        if hit:
            best, how, tok, conf = hit
            row.update(lon=float(best.lon), lat=float(best.lat), geocode_method=f"osm_place_{how}", geocode_confidence=conf,
                       geocode_note=f"token '{tok}' → OSM place={best.place} '{best['name']}' (town centre as proxy for market yard)")
        elif di is None:
            row["geocode_note"] = "district not matched to geoBoundaries ADM2 and no OSM place matched in the state"
        else:
            dd = dist.loc[di]
            row.update(lon=float(dd.c_lon), lat=float(dd.c_lat), geocode_method="district_centroid", geocode_confidence=0.25,
                       geocode_note=f"no OSM place matched; placed at centre of {dd.district_name} (APPROXIMATE)")
        res.append(row)
    return pd.concat([markets.reset_index(drop=True), pd.DataFrame(res)], axis=1)


def main() -> None:
    pbf = Path(sys.argv[1]) if len(sys.argv) > 1 else PBF
    a = load_arrivals()
    daily = aggregate(a)
    mk = daily.groupby(["state", "district", "market"], as_index=False).agg(first=("date", "min"), last=("date", "max"))
    mk["market_id"] = [hashlib.sha1(f"{s}|{d}|{m}".encode()).hexdigest()[:12] for s, d, m in zip(mk.state, mk.district, mk.market)]
    for crop in CROPS:
        sub = daily[daily.crop == crop].groupby(["state", "district", "market"])
        agg = sub.agg(t=("arrival_t", "sum"), days=("date", "nunique"), price=("modal_rs_q", "median")).reset_index()
        agg = agg.rename(columns={"t": f"{crop}_t", "days": f"{crop}_days", "price": f"{crop}_price_rs_q"})
        mk = mk.merge(agg, on=["state", "district", "market"], how="left")
    states, dist = boundaries()
    places = places_from_pbf(pbf)
    mk = geocode(mk, places, dist)
    ov = yaml.safe_load((ROOT / "config" / "market_overrides.yaml").read_text(encoding="utf-8"))["overrides"]
    for o in ov:
        hit = (mk.state == o["state"]) & (mk.market == o["market"])
        mk.loc[hit, ["lon", "lat", "geocode_method", "geocode_confidence", "geocode_note"]] = [
            o["lon"], o["lat"], "manual_override", 0.8, f"{o['note']} ({o['status']}, config/market_overrides.yaml)"]
    mk["district_geo"] = mk.district_idx.map(lambda i: dist.loc[int(i)].district_name if pd.notna(i) else None)
    daily = daily.merge(mk[["state", "district", "market", "market_id"]], on=["state", "district", "market"])

    OUT.mkdir(parents=True, exist_ok=True)
    mk.drop(columns=["district_idx"]).to_parquet(OUT / "markets.parquet", index=False)
    daily[["market_id", "crop", "date", "arrival_t", "modal_rs_q", "rows"]].to_parquet(OUT / "arrivals_daily.parquet", index=False)
    dist[["district_name", "state_name", "shapeID", "geometry"]].to_file(OUT / "districts.geojson", driver="GeoJSON")
    states[["state_name", "geometry"]].to_file(OUT / "states.geojson", driver="GeoJSON")
    rep = {
        "places_source": pbf.name, "markets": int(len(mk)),
        "by_method": {k: int(v) for k, v in mk.geocode_method.value_counts().items()},
        "district_unmatched": sorted(set(zip(mk.state[mk.district_idx.isna()], mk.district[mk.district_idx.isna()])))[:60],
        "arrival_rows": int(len(a)), "daily_rows": int(len(daily)),
        "period": [str(daily.date.min().date()), str(daily.date.max().date())],
    }
    (OUT / "markets_report.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=2, default=str)[:3000])


if __name__ == "__main__":
    main()
