"""Audit records for needs that are not fetched by a Phase-1 fetcher (road graph and OSM POIs are fetched
in Phase 2 by pipelines.build_graph, which overwrites these records with real counts)."""
from __future__ import annotations

from pipelines.common import AUDIT_DIR, AuditRecord, polite_get, write_audit

OVERPASS = ["https://overpass-api.de/api/status", "https://overpass.kumi.systems/api/status",
            "https://overpass.private.coffee/api/status"]


def run(refresh: bool = False) -> None:
    probes = []
    for u in OVERPASS:
        try:
            r = polite_get(u, retries=0, timeout=20)
            probes.append(f"{u} → HTTP {r.status_code}")
        except ConnectionError as e:
            probes.append(f"{u} → unreachable ({str(e)[:60]})")
    if not (AUDIT_DIR / "osm_roads.json").exists():
        write_audit("osm_roads", AuditRecord(
            need="Road network (drivable graph)", source_name="OpenStreetMap via OSMnx/Overpass",
            status="UNVERIFIED", access="Overpass API (OSMnx)", auth="none",
            licence="ODbL 1.0: attribution + share-alike for derived databases",
            coverage="not yet fetched (Phase 2)", tried=probes,
            fallback="Labelled SYNTHETIC_DEMO grid graph if OSM cannot be fetched (§9 step 9).",
            urls=["https://wiki.openstreetmap.org/wiki/Overpass_API"],
            rate_limits="Public Overpass instances are shared; main instance asks automated users to back off / self-host",
            flags=["ATTRIBUTION_REQUIRED", "SHARE_ALIKE_ODbL"]))
    if not (AUDIT_DIR / "osm_pois.json").exists():
        write_audit("osm_pois", AuditRecord(
            need="Warehouse / cold-storage / NGO / processing locations", source_name="OpenStreetMap via Overpass",
            status="UNVERIFIED", access="Overpass API", auth="none", licence="ODbL 1.0",
            coverage="not yet fetched (Phase 2)", tried=probes,
            fallback="Fictional 'Demo … DEMO' nodes tagged SYNTHETIC_DEMO for the demo only.",
            flags=["ATTRIBUTION_REQUIRED", "EXPECT_SPARSE_COVERAGE"]))
    write_audit("cold_chain_directory", AuditRecord(
        need="Hub / cold-storage capacity", source_name="Cold-chain directory (named in the deck, dataset unspecified)",
        status="MISSING", access="n/a", auth="n/a", licence="n/a", coverage="none",
        tried=["Web search 2026-10-24: NHB 'CISS' sanctioned-projects PDF (scanned table, old sanctions)",
               "Parliament answers: district counts 2018-21 (PDF), state totals only for 2025",
               "data.gov.in: state-wise cold storage counts (not district-level; needs key for API)"],
        why_failed="No machine-readable, current, facility-level list with capacities for the pilot districts.",
        fallback="capacity_kg left empty on nodes (never invented). Demo cold stores are fictional and labelled DEMO.",
        urls=["https://www.nhb.gov.in/doc/CISS12.pdf"], flags=["MISSING"]))
    write_audit("mandi_capacity", AuditRecord(
        need="Mandi physical capacity (for '% full' crowd meter)", source_name="None found",
        status="MISSING", access="n/a", auth="n/a", licence="n/a", coverage="none",
        tried=["Agmarknet master and report fields: no capacity field", "Agmarknet 'market profile' pages not examined"],
        why_failed="No verifiable capacity figure.",
        fallback="Crowd meter = today's arrivals ÷ trailing 14-day median arrivals for that market and commodity, "
                 "labelled exactly so. '% of capacity' is never shown.", flags=["MISSING"]))
    write_audit("traffic", AuditRecord(
        need="Congestion / disruption", source_name="No real-time or historical traffic source",
        status="MISSING", access="n/a", auth="n/a", licence="n/a", coverage="none",
        tried=["No free, licensable traffic feed for the region identified"],
        fallback="Seeded stochastic delay multipliers by road class and time of day (ASSUMPTION); never shown as observed traffic.",
        flags=["MODELLED_NOT_OBSERVED"]))
    write_audit("other_evidence", AuditRecord(
        need="Context evidence cited in the brief (WRI India 2024, RBI WPS 08/2024, NCCD 2015)",
        source_name="As cited in inputs/Source_Register_round1_brief.md", status="UNVERIFIED",
        access="not fetched by this pipeline", auth="n/a", licence="various",
        coverage="Used only as quoted (with the brief's caveats) on the Evidence & Limitations screen",
        tried=["Not re-fetched in Phase 1; the team's source register records the check level for each"],
        fallback="Shown with the brief's own check-level labels.", flags=["CITED_VIA_BRIEF"]))
    print("static audit records written; overpass probes:", probes)


if __name__ == "__main__":
    run()
