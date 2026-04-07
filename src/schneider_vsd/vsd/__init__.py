"""Schneider VSD model registry.

To add a new Schneider model, create a new module in this package
(e.g. atv320.py) with a class inheriting from VsdBase, and register
it in VSD_MODELS below.
"""

from .atv600 import ATV600

VSD_MODELS: dict[str, type] = {
    "atv600": ATV600,
}


def get_vsd_class(model_type: str) -> type:
    """Look up VSD class by model type string (case-insensitive)."""
    cls = VSD_MODELS.get(model_type.lower())
    if cls is None:
        available = ", ".join(VSD_MODELS.keys())
        raise ValueError(f"Unknown VSD type '{model_type}'. Available: {available}")
    return cls
