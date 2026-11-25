"""Galaxy map: coordinates, classification, sectors, and SVG rendering."""

from galaxy.config import CelestialObjectClassification
from galaxy.coords import CoordinateConverter
from galaxy.renderer import GalaxyMapGenerator
from galaxy.sectors import SectorAssigner

__all__ = [
    "CelestialObjectClassification",
    "CoordinateConverter",
    "GalaxyMapGenerator",
    "SectorAssigner",
]
