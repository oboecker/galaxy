"""Sector assignment from polar coordinates.

The generator's sector logic.
"""

import math


class SectorAssigner:
    """Finds the sector a point of the map lies in, by its polar coordinates
    about the centre."""
    
    def __init__(self, center_x: float, center_y: float):
        self.center_x = center_x
        self.center_y = center_y
        self.ring_width = 150
        self.num_rings = 15
        self.num_sectors = 24
        self.sector_angle = 360 / self.num_sectors
    
    def assign_sector(self, x: float, y: float) -> str | None:
        """The sector graphic point (`x`, `y`) lies in: "0" in the centre circle,
        else its beam letter and ring, "A7"; None beyond the outermost ring."""
        dx = x - self.center_x
        dy = y - self.center_y
        
        distance = math.sqrt(dx**2 + dy**2)
        
        if distance <= self.ring_width:
            return "0"
        
        ring = math.ceil((distance - self.ring_width) / self.ring_width)
        
        if ring > self.num_rings:
            return None
        
        # Counter-clockwise from 12 o'clock, as the wedges are drawn
        # (renderer: radians(-angle)) and the map's own hover script reads
        # them (atan2(-dx, -dy)). atan2(dx, -dy) ran clockwise and filed every
        # star in the mirrored sector — Sol in X7, not A7.
        angle_rad = math.atan2(-dx, -dy)
        angle_deg = math.degrees(angle_rad)
        
        if angle_deg < 0:
            angle_deg += 360
        
        sector_index = int(angle_deg / self.sector_angle) % self.num_sectors
        sector_letter = chr(ord('A') + sector_index)
        
        return f"{sector_letter}{ring}"

