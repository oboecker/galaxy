"""Galactic <-> graphic coordinate conversion.

Ported from the anchor constants in docs/conversion.js.
The scales are anisotropic (x ~0.042885, y ~-0.042208) because they are derived
by anchoring on Sol rather than from a single uniform factor. That ~1.6%
mismatch is reproduced deliberately: correcting it would move all 165 systems
on a finished piece of artwork.
"""
from typing import Tuple


class CoordinateConverter:
    """Handles conversion between galactic and graphic coordinate systems."""
    
    def __init__(self, center_x: float, center_y: float):
        # Reference points from conversion.js
        self.center_galactic = {'x': 0, 'y': 0, 'z': 0}
        self.center_graphic = {'x': center_x, 'y': center_y}
        self.sol_galactic = {'x': -513, 'y': 24995, 'z': 50}
        
        # Scale factors based on original 5600x5600 image
        original_center = 2800

        # Protect against division by zero
        if original_center == 0:
            raise ValueError("Original center cannot be zero")
        if center_x == 0 or center_y == 0:
            raise ValueError("Center coordinates must be non-zero")

        self.sol_graphic = {
            'x': center_x + (2778 - original_center) * (center_x / original_center),
            'y': center_y + (1745 - original_center) * (center_y / original_center)
        }
    
    def galactic_to_graphic(self, x: float, y: float, z: float = 0) -> Tuple[float, float]:
        """Convert galactic coordinates to graphic (SVG) coordinates."""
        dx = self.sol_graphic['x'] - self.center_graphic['x']
        dy = self.sol_graphic['y'] - self.center_graphic['y']
        
        fx = dx / self.sol_galactic['x']
        fy = dy / self.sol_galactic['y']
        
        nx = (x * fx) + self.center_graphic['x']
        ny = (y * fy) + self.center_graphic['y']
        
        return (nx, ny)
    
    def graphic_to_galactic(self, x: float, y: float, z: float = 0) -> Tuple[float, float]:
        """Convert graphic (SVG) coordinates to galactic coordinates."""
        dx = self.sol_graphic['x'] - self.center_graphic['x']
        dy = self.sol_graphic['y'] - self.center_graphic['y']
        
        fx = dx / self.sol_galactic['x']
        fy = dy / self.sol_galactic['y']
        
        sx = (x - self.center_graphic['x']) / fx
        sy = (y - self.center_graphic['y']) / fy
        
        return (sx, sy)

