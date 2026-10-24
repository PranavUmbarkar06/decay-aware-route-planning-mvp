"""Data pipelines. Makes `backend/` importable so pipelines share config + provenance types, and
uses the OS certificate store (truststore) so hosts with incomplete chains (e.g. censusindia.gov.in)
verify correctly. TLS verification is never disabled."""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    pass
