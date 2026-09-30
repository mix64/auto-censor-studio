"""Public image-processing API. No GUI initialization or network access."""

from .regions import Region, LABEL_NAMES, expanded_box, region_mask, region_contains, region_covers, suppress
from .images import load_image, minimum_block, fingerprint, render, atomic_export
from .projects import save_project, read_project, read_project_data

__all__ = [
    "Region",
    "LABEL_NAMES",
    "expanded_box",
    "region_mask",
    "region_contains",
    "region_covers",
    "suppress",
    "load_image",
    "minimum_block",
    "fingerprint",
    "render",
    "atomic_export",
    "save_project",
    "read_project",
    "read_project_data",
]
