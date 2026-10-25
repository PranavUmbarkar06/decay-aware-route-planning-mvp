"""Command line: `python -m app.cli load|reset-demo|experiments|report`.

`load` builds the database from the auditable CSVs (nodes.csv + USER_ENTERED review overrides) and, in demo mode,
seeds clearly fictional SYNTHETIC_DEMO users and consignments.
"""
from __future__ import annotations

import sys
import uuid

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import ROOT, app_config
from app.core.db import Base, engine, session
from app.core.provenance import Provenance
from app.core.security import Role, utcnow
from app.models import orm  # noqa: F401  (registers tables)
from app.models.orm import (
    Consignment,
    CustodyEvent,
    Handover,
    NgoProfile,
    Node,
    QualityEvent,
    RescueBroadcast,
    RescueOffer,
    User,
)

PROCESSED = ROOT / "data" / "processed"

# Fictional demo personas. Phone numbers use the reserved-looking +91 00000 prefix (no Indian mobile starts with 0).
DEMO_USERS = [
    ("demo-farmer", "+910000000001", Role.FARMER, "Demo Farmer 1", "FarmGatherPoint"),
    ("demo-supervisor", "+910000000002", Role.SUPERVISOR, "Demo Supervisor 1", "AssemblyMandi"),
    ("demo-warehouse", "+910000000003", Role.WAREHOUSE, "Demo Warehouse Owner 1", "DemoColdStore"),
    ("demo-dispatcher", "+910000000004", Role.DISPATCHER, "Demo Dispatcher 1", "AssemblyMandi"),
    ("demo-ngo", "+910000000005", Role.NGO, "Demo NGO Coordinator 1", "NGOSink:demo"),
    ("demo-driver", "+910000000006", Role.TRANSPORTER, "Demo Driver 1", None),
    ("demo-admin", "+910000000007", Role.ADMIN, "Demo Analyst 1", None),
]


def load_nodes(db: Session) -> int:
    df = pd.read_csv(PROCESSED / "nodes.csv", dtype={"snapped_graph_node": str})
    ov_path = PROCESSED / "node_overrides.csv"
    ov = pd.read_csv(ov_path).set_index("node_id") if ov_path.exists() else pd.DataFrame()
    # Idempotent upsert: re-running `load` refreshes nodes from nodes.csv without breaking users/lots that reference
    # them. Admin-imported places (USER_ENTERED) and the demo persona node are kept.
    seen: set[str] = set()
    for r in df.itertuples(index=False):
        seen.add(r.node_id)
        review = None
        lat, lon = (None if pd.isna(r.lat) else float(r.lat)), (None if pd.isna(r.lon) else float(r.lon))
        if len(ov) and r.node_id in ov.index:
            o = ov.loc[r.node_id]
            review = o["decision"]
            if review == "move":
                lat, lon = float(o["lat"]), float(o["lon"])
        db.merge(Node(node_id=r.node_id, node_type=r.node_type, name=r.name, lat=lat, lon=lon,
                    district=None if pd.isna(r.district) else r.district,
                    snapped_graph_node=None if pd.isna(r.snapped_graph_node) else str(r.snapped_graph_node).split(".")[0],
                    snap_distance_m=None if pd.isna(r.snap_distance_m) else float(r.snap_distance_m),
                    geocode_method=None if pd.isna(r.geocode_method) else r.geocode_method,
                    geocode_confidence=None if pd.isna(r.geocode_confidence) else float(r.geocode_confidence),
                    capacity_kg=None if pd.isna(r.capacity_kg) else float(r.capacity_kg),
                    capacity_source=None if pd.isna(r.capacity_source) else r.capacity_source,
                    provenance=r.provenance, source_manifest_id=r.source_manifest_id, needs_review=bool(r.needs_review),
                    review_status=review, notes=None if pd.isna(r.notes) else r.notes,
                    agmarknet_market_name=None if pd.isna(r.agmarknet_market_name) else r.agmarknet_market_name))
    db.flush()
    stale = [n for n in db.scalars(select(Node)) if n.node_id not in seen and n.provenance not in ("USER_ENTERED",)
             and n.node_id != "NDEMOCOLD0001"]
    for n in stale:
        try:
            with db.begin_nested():
                db.delete(n)
        except Exception:  # noqa: BLE001 - still referenced: keep it (it simply stops being refreshed)
            pass
    return len(df)


def _demo_cold_store(db: Session) -> Node:
    """A fictional cold store for the demo warehouse persona, placed at the same coordinates as the first routable
    real AssemblyMandi's snapped graph node (so it is routable), never at a real business."""
    n = db.get(Node, "NDEMOCOLD0001")
    if n:
        return n
    anchor = db.scalars(select(Node).where(Node.node_type == "ReceivingMarket", Node.needs_review.is_(False))
                        .order_by(Node.node_id)).first()
    n = Node(node_id="NDEMOCOLD0001", node_type="TransitStorageNode", name="Demo Cold Store 1 DEMO",
             lat=anchor.lat if anchor else None, lon=anchor.lon if anchor else None,
             district=anchor.district if anchor else None,
             snapped_graph_node=anchor.snapped_graph_node if anchor else None,
             snap_distance_m=anchor.snap_distance_m if anchor else None, geocode_method="manual_review",
             geocode_confidence=1.0, capacity_kg=50_000, capacity_source="SYNTHETIC_DEMO (fictional)",
             provenance=Provenance.SYNTHETIC_DEMO, source_manifest_id="synthetic:demo_persona", needs_review=False,
             notes="fictional node for the demo warehouse persona")
    db.add(n)
    db.flush()
    return n


def seed_demo(db: Session) -> dict:
    nodes = {t: db.scalars(select(Node).where(Node.node_type == t, Node.needs_review.is_(False)).order_by(Node.node_id)).first()
             for t in ("FarmGatherPoint", "AssemblyMandi", "ReceivingMarket")}
    demo_ngo = db.scalars(select(Node).where(Node.node_type == "NGOSink", Node.provenance == Provenance.SYNTHETIC_DEMO)).first()
    cold = _demo_cold_store(db)
    home = {"FarmGatherPoint": nodes["FarmGatherPoint"], "AssemblyMandi": nodes["AssemblyMandi"], "DemoColdStore": cold,
            "NGOSink:demo": demo_ngo}
    users = {}
    for handle, phone, role, name, where in DEMO_USERS:
        u = db.scalar(select(User).where(User.phone == phone))
        if u is None:
            hn = home.get(where) if where else None
            u = User(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"phl-demo:{handle}")), phone=phone, role=role.value, name=name,
                     language="en", district=hn.district if hn else None, home_node_id=hn.node_id if hn else None,
                     consent_at=utcnow(), created_at=utcnow(), provenance=Provenance.SYNTHETIC_DEMO)
            db.add(u)
        users[handle] = u
    db.flush()
    if demo_ngo is not None and db.get(NgoProfile, demo_ngo.node_id) is None:
        db.add(NgoProfile(node_id=demo_ngo.node_id, user_id=users["demo-ngo"].id, accepted_commodities="onion,orange,tomato",
                          daily_capacity_kg=2000, pickup_start_ist=7, pickup_end_ist=20, can_collect=True,
                          provenance=Provenance.SYNTHETIC_DEMO, updated_at=utcnow()))
    db.flush()
    return {"users": len(users), "cold_store": cold.node_id}


def reset_demo(db: Session) -> None:
    demo_ids = [c.id for c in db.scalars(select(Consignment).where(Consignment.provenance == Provenance.SYNTHETIC_DEMO))]
    if demo_ids:
        db.execute(delete(RescueOffer).where(RescueOffer.consignment_id.in_(demo_ids)))
        db.execute(delete(RescueBroadcast).where(RescueBroadcast.consignment_id.in_(demo_ids)))
        db.execute(delete(QualityEvent).where(QualityEvent.consignment_id.in_(demo_ids)))
        db.execute(delete(CustodyEvent).where(CustodyEvent.consignment_id.in_(demo_ids)))
        db.execute(delete(Handover).where(Handover.consignment_id.in_(demo_ids)))
        db.execute(delete(Consignment).where(Consignment.id.in_(demo_ids)))


def cmd_load() -> None:
    Base.metadata.create_all(engine())
    with session() as db:
        reset_demo(db)
        n = load_nodes(db)
        info = seed_demo(db) if app_config().runtime.demo_mode else {}
        db.commit()
    print(f"load: {n} nodes from nodes.csv; demo seed: {info}; db={engine().url}")


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "load"
    if cmd == "load":
        cmd_load()
    elif cmd == "reset-demo":
        with session() as db:
            reset_demo(db)
            db.commit()
        print("demo data reset")
    elif cmd in ("experiments", "report"):
        import importlib
        runner = importlib.import_module("app.simulation.runner")   # built in Phase 4
        return int(runner.main([cmd, *argv[1:]]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

