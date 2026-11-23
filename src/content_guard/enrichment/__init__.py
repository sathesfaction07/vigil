from .base import DetectedEntity, EntityEnricher
from .comprehend import ComprehendEnricher
from .google_nlp import GoogleNLPEnricher
from .local import LocalEnricher

ENRICHERS = {
    "comprehend": ComprehendEnricher,
    "google_nlp": GoogleNLPEnricher,
    "local": LocalEnricher,
    "none": None,
}


def get_enricher(name: str, **kwargs) -> EntityEnricher | None:
    if name == "none":
        return None
    cls = ENRICHERS.get(name)
    if not cls:
        available = ", ".join(ENRICHERS.keys())
        raise ValueError(f"Unknown enricher: {name}. Available: {available}")
    return cls(**kwargs)

# Re-exported: this module IS the package's public surface.
__all__ = [
    "ComprehendEnricher",
    "DetectedEntity",
    "EntityEnricher",
    "GoogleNLPEnricher",
    "LocalEnricher",
]
