"""Public image-processing API. No GUI initialization or network access."""

from .regions import Region, LABEL_NAMES, expanded_box, region_mask, region_contains, region_covers, suppress
from .images import load_image, default_block, fingerprint, render, atomic_export, overwrite_source
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
    "default_block",
    "fingerprint",
    "render",
    "atomic_export",
    "overwrite_source",
    "save_project",
    "read_project",
    "read_project_data",
]
