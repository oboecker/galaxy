"""Galaxy map SVG renderer.

Pan and zoom are the `interactive` option on the one renderer, with no
coordinate-box JS and no random spectral fallback, so the output is
reproducible.
"""

import hashlib
import math
import re
import sys
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from galaxy.fs import write_atomic
from galaxy import brightstars
from galaxy.config import CelestialObjectClassification
from galaxy.coords import CoordinateConverter
from galaxy.sectors import SectorAssigner

# A real star's dot against the catalogue's own: small, as on the 3D map.
REAL_SIZE = 0.35


class GalaxyMapGenerator:
    """Generates SVG galaxy map with sectors, grid, and star systems."""
    
    def __init__(self, width: int = 6000, height: int = 6000, interactive: bool = False):
        self.width = width
        self.height = height
        # When set, the SVG carries viewBox-based zoom/pan controls.  This is the
        # only behavioural difference the former zoom_and_pan script had that was
        # worth keeping; everything else it did differently was older.
        self.interactive = interactive
        self.center_x = width / 2
        self.center_y = height / 2
        
        self.converter = CoordinateConverter(self.center_x, self.center_y)
        self.assigner = SectorAssigner(self.center_x, self.center_y)
        
        # SVG namespaces
        self.svg_ns = 'http://www.w3.org/2000/svg'
        self.inkscape_ns = 'http://www.inkscape.org/namespaces/inkscape'

        # Register namespaces for proper serialization
        ET.register_namespace('inkscape', self.inkscape_ns)
        ET.register_namespace('sodipodi', 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd')

        self.svg = None
        # Store sector shapes to add later (after stars)
        self.pending_sector_shapes = {}
        # Track star count per sector for density calculation
        self.sector_star_counts = {}
        # Store star hover areas to add in overlay layer
        self.star_hover_areas = []

    def create_svg_root(self) -> ET.Element:
        """Create the root SVG element."""
        svg = ET.Element('svg', {
            'xmlns': self.svg_ns,
            'xmlns:inkscape': self.inkscape_ns,
            'width': str(self.width),
            'height': str(self.height),
            'viewBox': f'0 0 {self.width} {self.height}'
        })
        return svg
    
    def create_layer(self, label: str, layer_id: Optional[str] = None) -> ET.Element:
        """Create an Inkscape layer."""
        if layer_id is None:
            layer_id = label.lower().replace(' ', '_')
        
        layer = ET.Element('g', {
            f'{{{self.inkscape_ns}}}groupmode': 'layer',
            f'{{{self.inkscape_ns}}}label': label,
            'id': layer_id
        })
        return layer
    
    def create_background(self) -> ET.Element:
        """Create the background layer."""
        layer = self.create_layer('Background', 'background')
        
        rect = ET.SubElement(layer, 'rect', {
            'x': '0',
            'y': '0',
            'width': str(self.width),
            'height': str(self.height),
            'fill': '#262626',
            'id': 'background_rect'
        })
        
        return layer
    
    def create_labels(self, labels_data: List[Dict]) -> ET.Element:
        """Create the labels layer."""
        layer = self.create_layer('Labels', 'labels')
        
        for i, label_info in enumerate(labels_data):
            label_text = label_info.get('label', '')
            x = label_info.get('x', 0)
            y = label_info.get('y', 0)
            rotation = label_info.get('rotation', 0)
            
            label_id = label_text.lower().replace(' ', '_')
            
            text_elem = ET.SubElement(layer, 'text', {
                'x': str(x),
                'y': str(y),
                'font-family': 'Lithos Pro Regular',
                'font-size': '56',
                'fill': '#4d4d4d',
                'id': f'label_{label_id}',
                'text-anchor': 'start'
            })
            
            if rotation != 0:
                text_elem.set('transform', f'rotate({rotation})')

            text_elem.text = label_text
        
        return layer
    
    def create_grid(self) -> ET.Element:
        """Create the grid layer with center circle, rings, and radial beams."""
        layer = self.create_layer('Grid', 'grid')
        
        # Style for grid elements
        grid_style = 'fill:none;stroke:#000000;stroke-width:2'
        
        # Create center circle
        center_circle = ET.SubElement(layer, 'circle', {
            'cx': str(self.center_x),
            'cy': str(self.center_y),
            'r': '150',
            'style': grid_style,
            'id': 'center_circle'
        })
        
        # Create rings
        for ring_num in range(1, 16):
            radius = 150 + (ring_num * 150)
            ring = ET.SubElement(layer, 'circle', {
                'cx': str(self.center_x),
                'cy': str(self.center_y),
                'r': str(radius),
                'style': grid_style,
                'id': f'ring_{ring_num}'
            })
            
            # Add ring label
            label_y = self.center_y - radius + 75
            label_x = self.center_x + 10
            
            ring_label = ET.SubElement(layer, 'text', {
                'x': str(label_x),
                'y': str(label_y),
                'font-family': 'Lithos Pro Regular',
                'font-size': '24',
                'fill': '#666666',
                'id': f'ring_label_{ring_num}',
                'text-anchor': 'start'
            })
            ring_label.text = str(ring_num)
        
        # Create radial beams
        outer_radius = 150 + (15 * 150) + 150
        
        for beam_index in range(24):
            # Counter-clockwise: A at 0°, B at 15°, C at 30°, etc.
            # But we need to negate for counter-clockwise from top
            angle_deg = beam_index * 15
            # For counter-clockwise beams, use negative angle
            angle_rad = math.radians(-angle_deg)

            # Start at edge of center circle
            x1 = self.center_x + 150 * math.sin(angle_rad)
            y1 = self.center_y - 150 * math.cos(angle_rad)
            
            # End outside outermost ring
            x2 = self.center_x + outer_radius * math.sin(angle_rad)
            y2 = self.center_y - outer_radius * math.cos(angle_rad)
            
            beam = ET.SubElement(layer, 'line', {
                'x1': str(x1),
                'y1': str(y1),
                'x2': str(x2),
                'y2': str(y2),
                'style': grid_style,
                'id': f'beam_{beam_index}'
            })
            
            # Add beam label (letter A-X)
            letter = chr(ord('A') + beam_index)
            
            # Label positioned at 7.5 degrees offset (counter-clockwise), inside center circle
            label_angle_deg = -(angle_deg + 7.5)  # Negative for counter-clockwise
            label_angle_rad = math.radians(label_angle_deg)
            label_radius = 130
            
            label_x = self.center_x + label_radius * math.sin(label_angle_rad)
            label_y = self.center_y - label_radius * math.cos(label_angle_rad)
            
            beam_label = ET.SubElement(layer, 'text', {
                'x': str(label_x),
                'y': str(label_y),
                'font-family': 'Lithos Pro Regular',
                'font-size': '24',
                'fill': '#666666',
                'id': f'beam_label_{letter}',
                'text-anchor': 'middle',
                'dominant-baseline': 'middle'
            })
            beam_label.text = letter
        
        return layer
    
    def create_territories(self, territories: List[Dict]) -> ET.Element:
        """Nation territories, projected onto the galactic plane.

        Computed by galaxy/territories.py. Nations stacked in z overlap here by
        design, so each keeps its full outline and its own hatch angle: two
        translucent fills alone would blend into what reads as a third nation.
        """
        layer = self.create_layer('Territories', 'territories')
        defs = ET.SubElement(layer, 'defs')
        for t in territories:
            nid = t['nation']
            pattern = ET.SubElement(defs, 'pattern', {
                'id': f'hatch_{nid}', 'patternUnits': 'userSpaceOnUse',
                'width': '6', 'height': '6',
                'patternTransform': f"rotate({t['hatch']:.1f})",
            })
            ET.SubElement(pattern, 'line', {
                'x1': '0', 'y1': '0', 'x2': '0', 'y2': '6',
                'stroke': t['color'], 'stroke-width': '1', 'stroke-opacity': '0.55',
            })

        for t in territories:
            nid = t['nation']
            group = ET.SubElement(layer, 'g', {'id': f'territory_{nid}', 'class': 'territory'})
            d = ' '.join(self._ring_path(ring) for polygon in t['footprint'] for ring in polygon)
            common = {'d': d, 'fill-rule': 'evenodd'}
            ET.SubElement(group, 'path', {**common, 'fill': t['color'], 'fill-opacity': '0.10'})
            ET.SubElement(group, 'path', {**common, 'fill': f'url(#hatch_{nid})'})
            ET.SubElement(group, 'path', {
                **common, 'fill': 'none', 'stroke': t['color'],
                'stroke-width': '1.5', 'stroke-opacity': '0.85',
            })
            if t.get('label'):
                x, y = self.converter.galactic_to_graphic(*t['label'])
                label = ET.SubElement(group, 'text', {
                    'x': f'{x:.1f}', 'y': f'{y:.1f}',
                    'font-family': 'Lithos Pro Regular', 'font-size': '18',
                    'letter-spacing': '4', 'text-anchor': 'middle',
                    'fill': t['color'], 'fill-opacity': '0.9',
                })
                label.text = t['name'].upper()
        return layer

    def create_nebulae(self, items: List[Dict]) -> ET.Element:
        """Nebulae, projected onto the galactic plane: each its ellipse in the
        plane (the first two half-axes, turned by the tilt's third angle),
        blurred, in its kind's colour (galaxy.nebulae), its name beneath. Under
        the sectors, so the stars stay on top. A nebula of a few light years is
        a fraction of a unit here: at least a few units, so it shows."""
        from galaxy import nebulae
        layer = self.create_layer('Nebulae', 'nebulae')
        defs = ET.SubElement(layer, 'defs')
        blur = ET.SubElement(defs, 'filter', {'id': 'nebula_blur', 'x': '-50%', 'y': '-50%',
                                              'width': '200%', 'height': '200%'})
        ET.SubElement(blur, 'feGaussianBlur', {'stdDeviation': '2.5'})
        for n in items:
            x, y = self.converter.galactic_to_graphic(n['x'], n['y'])
            ex, _ = self.converter.galactic_to_graphic(n['x'] + n['size'][0], n['y'])
            _, ey = self.converter.galactic_to_graphic(n['x'], n['y'] + n['size'][1])
            rx, ry = max(abs(ex - x), 4.0), max(abs(ey - y), 4.0)
            colour = nebulae.colour(n)
            angle = (n.get('tilt') or [0, 0, 0])[2]
            group = ET.SubElement(layer, 'g', {'class': 'nebula', 'id': f"nebula_{n.get('id', '')}"})
            ellipse = {'cx': f'{x:.1f}', 'cy': f'{y:.1f}', 'rx': f'{rx:.1f}', 'ry': f'{ry:.1f}',
                       'fill': colour, 'fill-opacity': '0.45' if n.get('kind') != 'dark' else '0.75',
                       'filter': 'url(#nebula_blur)'}
            if angle:
                ellipse['transform'] = f'rotate({angle:g} {x:.1f} {y:.1f})'
            ET.SubElement(group, 'ellipse', ellipse)
            label = ET.SubElement(group, 'text', {
                # Small, as the star labels are where stars crowd (2.5 to 8).
                'x': f'{x:.1f}', 'y': f'{y + ry + 5:.1f}', 'text-anchor': 'middle',
                'font-family': 'Lithos Pro Regular', 'font-size': '3.5', 'fill': colour, 'fill-opacity': '0.8',
            })
            label.text = n['name']
        return layer

    def _ring_path(self, ring: List[List[float]]) -> str:
        """A ring of galactic (x, y) points as a closed SVG path in graphic coordinates."""
        points = [self.converter.galactic_to_graphic(x, y) for x, y in ring]
        return 'M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x, y in points) + ' Z'

    def create_mouse_coordinates_display(self) -> ET.Element:
        """Create a mouse coordinates display layer."""
        layer = self.create_layer('Mouse Coordinates', 'mouse_coordinates')

        # Create a group for the coordinate display that will follow the mouse
        coord_group = ET.SubElement(layer, 'g', {
            'id': 'coord_display_group',
            'class': 'coord-display',
            'opacity': '0',
            'pointer-events': 'none'
        })

        # Background rectangle for better readability
        bg_rect = ET.SubElement(coord_group, 'rect', {
            'x': '0',
            'y': '0',
            'width': '220',
            'height': '85',
            'fill': '#1a1a1a',
            'stroke': '#4d4d4d',
            'stroke-width': '2',
            'rx': '5',
            'ry': '5',
            'opacity': '0.95',
            'id': 'coord_bg'
        })

        # Graphic coordinates text
        graphic_label = ET.SubElement(coord_group, 'text', {
            'x': '10',
            'y': '20',
            'font-family': 'Lithos Pro Regular',
            'font-size': '11',
            'fill': '#aaaaaa',
            'id': 'coord_graphic_label'
        })
        graphic_label.text = 'Graphic:'

        graphic_value = ET.SubElement(coord_group, 'text', {
            'x': '80',
            'y': '20',
            'font-family': 'monospace',
            'font-size': '11',
            'fill': '#00ff00',
            'id': 'coord_graphic_value'
        })
        graphic_value.text = '(0, 0)'

        # Galactic coordinates text
        galactic_label = ET.SubElement(coord_group, 'text', {
            'x': '10',
            'y': '40',
            'font-family': 'Lithos Pro Regular',
            'font-size': '11',
            'fill': '#aaaaaa',
            'id': 'coord_galactic_label'
        })
        galactic_label.text = 'Galactic:'

        galactic_value = ET.SubElement(coord_group, 'text', {
            'x': '80',
            'y': '40',
            'font-family': 'monospace',
            'font-size': '11',
            'fill': '#ffaa00',
            'id': 'coord_galactic_value'
        })
        galactic_value.text = '(0, 0)'

        # Sector text
        sector_label = ET.SubElement(coord_group, 'text', {
            'x': '10',
            'y': '60',
            'font-family': 'Lithos Pro Regular',
            'font-size': '11',
            'fill': '#aaaaaa',
            'id': 'coord_sector_label'
        })
        sector_label.text = 'Sector:'

        sector_value = ET.SubElement(coord_group, 'text', {
            'x': '80',
            'y': '60',
            'font-family': 'monospace',
            'font-size': '11',
            'font-weight': 'bold',
            'fill': '#ff0000',
            'id': 'coord_sector_value'
        })
        sector_value.text = '-'

        return layer

    def create_legend(self) -> ET.Element:
        """Create a legend layer showing star classifications."""
        layer = self.create_layer('Legend', 'legend')

        # Legend position (top-right corner)
        legend_x = self.width - 300
        legend_y = 100

        # Legend background
        bg_width = 280
        bg_height = 320
        bg_rect = ET.SubElement(layer, 'rect', {
            'x': str(legend_x - 10),
            'y': str(legend_y - 10),
            'width': str(bg_width),
            'height': str(bg_height),
            'fill': '#1a1a1a',
            'stroke': '#4d4d4d',
            'stroke-width': '2',
            'rx': '5',
            'ry': '5',
            'opacity': '0.9',
            'id': 'legend_background'
        })

        # Legend title
        title = ET.SubElement(layer, 'text', {
            'x': str(legend_x + bg_width / 2 - 10),
            'y': str(legend_y + 20),
            'font-family': 'Lithos Pro Regular',
            'font-size': '16',
            'font-weight': 'bold',
            'fill': '#ffffff',
            'id': 'legend_title',
            'text-anchor': 'middle'
        })
        title.text = 'Star Classification'

        # Add each star type
        y_offset = legend_y + 50
        line_height = 30

        for star_class in ['O', 'B', 'A', 'F', 'G', 'K', 'M']:
            props = CelestialObjectClassification.get_properties('star', star_class)

            # Star example dot
            dot = ET.SubElement(layer, 'circle', {
                'cx': str(legend_x + 20),
                'cy': str(y_offset),
                'r': str(props['radius'] * 1.5),
                'fill': props['color'],
                'id': f'legend_star_{star_class}'
            })

            # Star class label
            class_label = ET.SubElement(layer, 'text', {
                'x': str(legend_x + 40),
                'y': str(y_offset),
                'font-family': 'Lithos Pro Regular',
                'font-size': '14',
                'font-weight': 'bold',
                'fill': props['color'],
                'id': f'legend_label_{star_class}',
                'dominant-baseline': 'middle'
            })
            class_label.text = f'Class {star_class}'

            # Temperature
            temp_label = ET.SubElement(layer, 'text', {
                'x': str(legend_x + 110),
                'y': str(y_offset),
                'font-family': 'Lithos Pro Regular',
                'font-size': '10',
                'fill': '#cccccc',
                'id': f'legend_temp_{star_class}',
                'dominant-baseline': 'middle'
            })
            temp_label.text = props['temperature']

            y_offset += line_height

        # Add unclassified star info
        y_offset += 10

        unclass_dot = ET.SubElement(layer, 'circle', {
            'cx': str(legend_x + 20),
            'cy': str(y_offset),
            'r': '1.0',
            'fill': '#ffffff',
            'id': 'legend_star_unclassified'
        })

        unclass_label = ET.SubElement(layer, 'text', {
            'x': str(legend_x + 40),
            'y': str(y_offset),
            'font-family': 'Lithos Pro Regular',
            'font-size': '12',
            'fill': '#ffffff',
            'id': 'legend_label_unclassified',
            'dominant-baseline': 'middle'
        })
        unclass_label.text = 'Unclassified'

        return layer

    def create_sectors(self, sector_names: Dict[str, str] = None) -> ET.Element:
        """Create the sectors layer with individual sector sublayers."""
        layer = self.create_layer('Sectors', 'sectors')
        
        if sector_names is None:
            sector_names = {}
        
        # Create center sector with clickable area
        self.create_sector_layer(layer, '0', sector_names.get('0', None))
        
        # Create ring sectors
        for ring_num in range(1, 16):
            for beam_index in range(24):
                letter = chr(ord('A') + beam_index)
                sector_id = f"{letter}{ring_num}"
                sector_name = sector_names.get(sector_id, None)
                self.create_sector_layer(layer, sector_id, sector_name)
        
        return layer
    
    def create_sector_layer(self, parent: ET.Element, sector_id: str, sector_name: Optional[str] = None):
        """Add sector `sector_id`'s layer to `parent`, with its permanent name
        where it has one and its hover label; its clickable shape waits in
        pending_sector_shapes for `_add_sector_shapes`."""
        # Calculate sector center for label placement and sector boundaries
        if sector_id == '0':
            x = self.center_x
            y = self.center_y
            # Create clickable circle for center sector
            sector_shape = self._create_center_sector_shape()
        else:
            letter = sector_id[0]
            ring = int(sector_id[1:])

            beam_index = ord(letter) - ord('A')
            # Counter-clockwise: negative angle
            angle_deg = -(beam_index * 15 + 7.5)
            angle_rad = math.radians(angle_deg)

            radius = 150 + (ring - 0.5) * 150

            x = self.center_x + radius * math.sin(angle_rad)
            y = self.center_y - radius * math.cos(angle_rad)

            # Create clickable wedge shape for this sector
            sector_shape = self._create_sector_wedge(letter, ring, sector_name)

        sector_layer = ET.SubElement(parent, 'g', {
            f'{{{self.inkscape_ns}}}groupmode': 'layer',
            f'{{{self.inkscape_ns}}}label': sector_id,
            'id': f'sector_{sector_id}',
            'class': 'sector'
        })
        
        # Add permanent sector name if provided (with class to prevent duplication on hover)
        if sector_name:
            name_text = ET.SubElement(sector_layer, 'text', {
                'x': str(x),
                'y': str(y),
                'font-family': 'Lithos Pro Regular',
                'font-size': '8',
                'fill': '#ff0000',
                'id': f'sector_name_{sector_id}',
                'class': 'sector-name-permanent',
                'text-anchor': 'middle',
                'dominant-baseline': 'middle',
                'pointer-events': 'none'
            })
            name_text.text = sector_name

        # Add hover label for sector ID (always, but hidden by default)
        hover_label = ET.SubElement(sector_layer, 'text', {
            'x': str(x),
            'y': str(y),
            'font-family': 'Lithos Pro Regular',
            'font-size': '18',
            'fill': '#ff0000',
            'id': f'sector_hover_label_{sector_id}',
            'class': 'sector-hover-label',
            'text-anchor': 'middle',
            'dominant-baseline': 'middle',
            'opacity': '0',
            'pointer-events': 'none'
        })
        hover_label.text = sector_id
        self.pending_sector_shapes[f'sector_{sector_id}'] = sector_shape

    def _create_center_sector_shape(self) -> ET.Element:
        """Create a clickable circle for the center sector."""
        circle = ET.Element('circle', {
            'cx': str(self.center_x),
            'cy': str(self.center_y),
            'r': '150',
            'fill': 'transparent',
            'stroke': 'none',
            'pointer-events': 'all',
            'class': 'sector-shape',
            'id': 'sector_shape_0'
        })
        return circle

    def _create_sector_wedge(self, letter: str, ring: int, sector_name: Optional[str] = None) -> ET.Element:
        """Create a clickable wedge shape for a sector."""
        beam_index = ord(letter) - ord('A')

        # Counter-clockwise: negative angles
        # For proper wedge drawing, start should be less negative than end
        start_angle = -(beam_index * 15)
        end_angle = -((beam_index + 1) * 15)  # More negative

        # Inner and outer radii
        inner_radius = 150 + (ring - 1) * 150
        outer_radius = 150 + ring * 150

        # Convert to radians
        start_rad = math.radians(start_angle)
        end_rad = math.radians(end_angle)

        # Calculate path points
        # We want to draw from start to end going counter-clockwise
        # So we go: outer_start -> outer_end (ccw arc) -> inner_end -> inner_start (cw arc back)
        outer_start_x = self.center_x + outer_radius * math.sin(start_rad)
        outer_start_y = self.center_y - outer_radius * math.cos(start_rad)

        outer_end_x = self.center_x + outer_radius * math.sin(end_rad)
        outer_end_y = self.center_y - outer_radius * math.cos(end_rad)

        inner_end_x = self.center_x + inner_radius * math.sin(end_rad)
        inner_end_y = self.center_y - inner_radius * math.cos(end_rad)

        inner_start_x = self.center_x + inner_radius * math.sin(start_rad)
        inner_start_y = self.center_y - inner_radius * math.cos(start_rad)

        # Create SVG path for wedge
        # Start at outer edge, draw counter-clockwise arc to end,
        # then straight line to inner edge, then clockwise arc back
        path_data = f"M {outer_start_x},{outer_start_y} "
        path_data += f"A {outer_radius},{outer_radius} 0 0,0 {outer_end_x},{outer_end_y} "
        path_data += f"L {inner_end_x},{inner_end_y} "
        path_data += f"A {inner_radius},{inner_radius} 0 0,1 {inner_start_x},{inner_start_y} "
        path_data += "Z"

        if sector_name:
            sector_color = '#ff0000'
        else:
            sector_color = 'none'

        path = ET.Element('path', {
            'd': path_data,
            'fill': 'transparent',
            'stroke': f'{sector_color}',
            'stroke-width': '2',
            'pointer-events': 'all',
            'class': 'sector-shape',
            'id': f'sector_shape_{letter}{ring}'
        })

        return path

    def _create_black_hole(self, parent: ET.Element, x: float, y: float, obj_id: str, obj_props: Dict):
        """Create a black hole with accretion disk effect."""
        obj_radius = obj_props['radius']
        secondary_color = obj_props.get('secondary_color', '#ff4500')

        # Outer accretion disk glow (orange/red)
        outer_glow = ET.SubElement(parent, 'circle', {
            'cx': str(x),
            'cy': str(y),
            'r': str(obj_radius * 2.5),
            'fill': secondary_color,
            'opacity': '0.2',
            'pointer-events': 'none',
            'id': f'object_accretion_outer_{obj_id}',
            'class': 'black-hole-accretion-outer'
        })

        # Middle accretion disk (brighter)
        middle_disk = ET.SubElement(parent, 'circle', {
            'cx': str(x),
            'cy': str(y),
            'r': str(obj_radius * 1.5),
            'fill': secondary_color,
            'opacity': '0.4',
            'pointer-events': 'none',
            'id': f'object_accretion_middle_{obj_id}',
            'class': 'black-hole-accretion-middle'
        })

        # Inner bright ring
        inner_ring = ET.SubElement(parent, 'circle', {
            'cx': str(x),
            'cy': str(y),
            'r': str(obj_radius * 1.2),
            'fill': 'none',
            'stroke': secondary_color,
            'stroke-width': '0.5',
            'opacity': '0.8',
            'pointer-events': 'none',
            'id': f'object_accretion_ring_{obj_id}',
            'class': 'black-hole-accretion-ring'
        })

        # Central black hole (pure black)
        black_hole = ET.SubElement(parent, 'circle', {
            'cx': str(x),
            'cy': str(y),
            'r': str(obj_radius),
            'fill': '#000000',
            'stroke': secondary_color,
            'stroke-width': '0.3',
            'pointer-events': 'none',
            'id': f'object_dot_{obj_id}',
            'class': 'object-dot black-hole-core'
        })

    def _calculate_sector_densities(self, celestial_objects: List[Dict]) -> Dict[str, int]:
        """Calculate the number of stars per sector for density-based font sizing."""
        sector_counts = {}

        for obj in celestial_objects:
            coord_system = obj.get('coordinate_system', 'graphic')

            if coord_system == 'galactic':
                x_gal = obj.get('x', 0)
                y_gal = obj.get('y', 0)
                z_gal = obj.get('z', 0)
                x, y = self.converter.galactic_to_graphic(x_gal, y_gal, z_gal)
            else:
                x = obj.get('x', 0)
                y = obj.get('y', 0)

            sector_id = self.assigner.assign_sector(x, y)
            if sector_id:
                sector_counts[sector_id] = sector_counts.get(sector_id, 0) + 1

        return sector_counts

    def _calculate_nearest_neighbor_distance(self, x: float, y: float, all_positions: List[Tuple[float, float]]) -> float:
        """Calculate the distance to the nearest neighbor star."""
        min_distance = float('inf')

        for other_x, other_y in all_positions:
            # Skip self
            if other_x == x and other_y == y:
                continue

            distance = math.sqrt((x - other_x)**2 + (y - other_y)**2)
            if distance < min_distance:
                min_distance = distance

        return min_distance if min_distance != float('inf') else 100.0  # Default to 100 if no neighbors

    def _get_label_font_size_from_distance(self, nearest_distance: float) -> float:
        """Calculate appropriate font size based on distance to nearest neighbor."""
        # Base font size
        base_size = 6.0
        min_size = 2.5
        max_size = 8.0

        # Distance thresholds (in pixels)
        # If nearest star is > 60px away, use max size
        # If nearest star is < 15px away, use min size
        if nearest_distance >= 60:
            return max_size
        elif nearest_distance <= 15:
            return min_size
        else:
            # Linear interpolation between min and max based on distance
            # Scale: 15px -> min_size, 60px -> max_size
            ratio = (nearest_distance - 15) / (60 - 15)
            return min_size + (max_size - min_size) * ratio

    def _get_type_label_font_size_from_distance(self, nearest_distance: float) -> float:
        """Calculate appropriate type label font size based on distance to nearest neighbor."""
        # Type labels are smaller than main labels
        # Base proportions to main label
        base_size = 3.5
        min_size = 1.8
        max_size = 5.0

        if nearest_distance >= 60:
            return max_size
        elif nearest_distance <= 15:
            return min_size
        else:
            ratio = (nearest_distance - 15) / (60 - 15)
            return min_size + (max_size - min_size) * ratio

    def _get_label_opacity_from_distance(self, nearest_distance: float) -> float:
        """Calculate label opacity based on distance to nearest neighbor."""
        # Reduce opacity when stars are very close together
        if nearest_distance >= 30:
            return 1.0  # Full opacity when well-spaced
        elif nearest_distance <= 10:
            return 0.6  # More transparent when very crowded
        else:
            # Linear interpolation
            ratio = (nearest_distance - 10) / (30 - 10)
            return 0.6 + (1.0 - 0.6) * ratio

    def add_celestial_objects(self, sectors_layer: ET.Element, celestial_objects: List[Dict]):
        """Add celestial objects (stars and special objects) to their respective sectors."""
        # First pass: calculate sector densities (kept for backwards compatibility)
        self.sector_star_counts = self._calculate_sector_densities(celestial_objects)

        # Build list of all star positions for nearest neighbor calculation
        all_positions = []
        out_of_bounds_count = 0
        for obj in celestial_objects:
            coord_system = obj.get('coordinate_system', 'graphic')
            if coord_system == 'galactic':
                x_gal = obj.get('x', 0)
                y_gal = obj.get('y', 0)
                z_gal = obj.get('z', 0)
                x, y = self.converter.galactic_to_graphic(x_gal, y_gal, z_gal)
            else:
                x = obj.get('x', 0)
                y = obj.get('y', 0)
            all_positions.append((x, y))

        for obj in celestial_objects:
            name = obj.get('name', 'Unknown')
            coord_system = obj.get('coordinate_system', 'graphic')
            object_type = obj.get('object_type', 'star')  # Defaults to 'star'
            # Get spectral class, or generate a deterministic one based on star name
            spectral_class = obj.get('spectral_class', None)
            if spectral_class is None:
                # Generate reproducible spectral class based on star name
                spectral_types = ['O', 'B', 'A', 'F', 'G', 'K', 'M']
                # Python salts str hashing per process, so the original hash()
                # here was not in fact reproducible run to run.  It never showed
                # because every system in galaxy.json carries a spectral_class,
                # leaving this branch dead — but a single system added without
                # one would have made the output differ on every run.  A stable
                # digest keeps the same intent and actually delivers it.
                name_hash = int(hashlib.md5(name.encode('utf-8')).hexdigest(), 16) % len(spectral_types)
                spectral_class = spectral_types[name_hash]

            if coord_system == 'galactic':
                x_gal = obj.get('x', 0)
                y_gal = obj.get('y', 0)
                z_gal = obj.get('z', 0)
                x, y = self.converter.galactic_to_graphic(x_gal, y_gal, z_gal)
            else:
                x = obj.get('x', 0)
                y = obj.get('y', 0)

            # Find which sector this star belongs to
            sector_id = self.assigner.assign_sector(x, y)
            
            if sector_id is None:
                out_of_bounds_count += 1
                distance = math.sqrt((x - self.center_x)**2 + (y - self.center_y)**2)
                max_distance = 150 + (15 * 150)
                print(f"Warning: {object_type.capitalize()} '{name}' at graphics ({x:.1f}, {y:.1f}) is outside valid range (distance: {distance:.1f}, max: {max_distance:.1f})", file=sys.stderr)
                continue
            
            # Find the sector layer
            sector_layer = sectors_layer.find(f".//*[@id='sector_{sector_id}']")
            
            if sector_layer is None:
                print(f"Warning: Sector layer '{sector_id}' not found for {object_type} '{name}'", file=sys.stderr)
                continue
            
            # Get object properties
            obj_props = CelestialObjectClassification.get_properties(object_type, spectral_class)
            obj_color = obj_props['color']
            obj_radius = obj_props['radius']
            obj_icon = obj_props.get('icon', 'star')
            has_glow = obj_props.get('has_glow', False)
            # The real sky's stars: small, no glow, named on hover.
            real = brightstars.is_real(obj)
            if real:
                obj_radius *= REAL_SIZE
                has_glow = False

            # Create object group
            obj_id = name.lower().replace(" ", "_").replace("-", "_")
            obj_group = ET.SubElement(sector_layer, 'g', {
                f'{{{self.inkscape_ns}}}groupmode': 'layer',
                f'{{{self.inkscape_ns}}}label': name,
                'id': f'object_{obj_id}',
                'class': f'celestial-object {object_type}' + (' real-star' if real else ''),
                'data-object-type': object_type,
                'data-spectral-class': spectral_class if spectral_class else 'none'
            })
            
            # Special rendering for black holes
            if object_type == 'black_hole':
                self._create_black_hole(obj_group, x, y, obj_id, obj_props)
            else:
                # Add glow effect for objects with has_glow=True
                if has_glow:
                    glow = ET.SubElement(obj_group, 'circle', {
                        'cx': str(x),
                        'cy': str(y),
                        'r': str(obj_radius * 2),
                        'fill': obj_color,
                        'opacity': '0.3',
                        'pointer-events': 'none',
                        'id': f'object_glow_{obj_id}',
                        'class': 'object-glow'
                    })

                # Add visible object dot with color and size based on type
                circle = ET.SubElement(obj_group, 'circle', {
                    'cx': str(x),
                    'cy': str(y),
                    'r': str(obj_radius),
                    'fill': obj_color,
                    'pointer-events': 'none',
                    'id': f'object_dot_{obj_id}',
                    'class': 'object-dot'
                })

            # Add object label (permanently visible, color matched to object)
            # For black holes, use secondary color for visibility
            label_color = obj_props.get('secondary_color', obj_color) if object_type == 'black_hole' else obj_color
            label_offset = obj_radius + 1.5

            # Calculate dynamic font size and opacity based on nearest neighbor distance
            nearest_distance = self._calculate_nearest_neighbor_distance(x, y, all_positions)
            label_font_size = self._get_label_font_size_from_distance(nearest_distance)
            label_opacity = self._get_label_opacity_from_distance(nearest_distance)

            label = ET.SubElement(obj_group, 'text', {
                'x': str(x + label_offset),
                'y': str(y),
                'font-family': 'Lithos Pro Regular',
                'font-size': str(label_font_size),
                'fill': label_color,
                'opacity': str(label_opacity),
                'id': f'object_label_{obj_id}',
                'class': 'object-label',
                'dominant-baseline': 'middle',
                'pointer-events': 'none'
            })
            label.text = name

            # Add type label for special objects (non-stars) only
            if object_type != 'star':
                type_text = f'[{obj_props["description"]}]'

                # Calculate dynamic font size for type label based on spacing
                type_font_size = self._get_type_label_font_size_from_distance(nearest_distance)
                type_opacity = label_opacity * 0.7  # Slightly more transparent than main label

                type_label = ET.SubElement(obj_group, 'text', {
                    'x': str(x + label_offset),
                    'y': str(y + 6),
                    'font-family': 'Lithos Pro Regular',
                    'font-size': str(type_font_size),
                    'fill': label_color,
                    'opacity': str(type_opacity),
                    'id': f'object_type_{obj_id}',
                    'class': 'object-type-label',
                    'dominant-baseline': 'hanging',
                    'pointer-events': 'none'
                })
                type_label.text = type_text

            # Store hover area data for overlay layer
            # Use a larger radius for easier hovering (minimum 4px)
            hover_radius = max(4, obj_radius * 3)
            self.star_hover_areas.append({
                'x': x,
                'y': y,
                'radius': hover_radius,
                'obj_id': obj_id,
                'name': name
            })

    def _add_sector_shapes(self, sectors_layer: ET.Element):
        """Add sector shapes so they're below stars in z-order (drawn first)."""
        # Add all pending sector shapes
        for sector_id, shape in self.pending_sector_shapes.items():
            sector = sectors_layer.find(f".//*[@id='{sector_id}']")
            if sector is not None:
                # Insert the shape at the beginning so it's drawn first (below stars)
                sector.insert(0, shape)
        # Clear the dictionary
        self.pending_sector_shapes.clear()

    def create_star_hover_overlay(self) -> ET.Element:
        """Create an overlay layer with larger hit areas for star hover effects."""
        layer = self.create_layer('Star Hover Areas', 'star_hover_areas')

        for hover_data in self.star_hover_areas:
            # Create invisible circle with larger radius for easier hovering
            hover_circle = ET.SubElement(layer, 'circle', {
                'cx': str(hover_data['x']),
                'cy': str(hover_data['y']),
                'r': str(hover_data['radius']),
                'fill': 'transparent',
                'stroke': 'none',
                'pointer-events': 'all',
                'class': 'star-hover-area',
                'id': f'hover_{hover_data["obj_id"]}',
                'data-target': f'object_{hover_data["obj_id"]}',
                'style': 'cursor: pointer;'
            })

        return layer

    def add_javascript(self):
        """Add the map's script: the galactic coordinates and sector under the
        mouse, the stars' hover effects, and with `interactive` the zoom/pan."""
        script = ET.Element('script', {'type': 'text/javascript'})
        # Pass converter parameters to JavaScript
        script.text = f"""
        // Coordinate conversion parameters
        const centerGraphic = {{ x: {self.center_x}, y: {self.center_y} }};
        const solGraphic = {{ x: {self.converter.sol_graphic['x']}, y: {self.converter.sol_graphic['y']} }};
        const solGalactic = {{ x: {self.converter.sol_galactic['x']}, y: {self.converter.sol_galactic['y']}, z: {self.converter.sol_galactic['z']} }};
        
        // Sector assignment parameters
        const ringWidth = {self.assigner.ring_width};
        const numRings = {self.assigner.num_rings};
        const numSectors = {self.assigner.num_sectors};
        const sectorAngle = {self.assigner.sector_angle};
        
        function graphicToGalactic(x, y) {{
            const dx = solGraphic.x - centerGraphic.x;
            const dy = solGraphic.y - centerGraphic.y;
            const fx = dx / solGalactic.x;
            const fy = dy / solGalactic.y;
            const sx = (x - centerGraphic.x) / fx;
            const sy = (y - centerGraphic.y) / fy;
            return {{ x: sx, y: sy }};
        }}
        
        function assignSector(x, y) {{
            const dx = x - centerGraphic.x;
            const dy = y - centerGraphic.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance <= ringWidth) {{
                return '0';
            }}
            
            const ring = Math.ceil((distance - ringWidth) / ringWidth);
            
            if (ring > numRings) {{
                return null;
            }}
            
            // Counter-clockwise: calculate angle from top (12 o'clock)
            // atan2(dx, -dy) gives clockwise angles, so negate dx for counter-clockwise
            let angleRad = Math.atan2(-dx, -dy);
            let angleDeg = angleRad * 180 / Math.PI;
            
            // Normalize to 0-360 range
            if (angleDeg < 0) {{
                angleDeg += 360;
            }}
            
            // Calculate sector index (counter-clockwise from top)
            const sectorIndex = Math.floor(angleDeg / sectorAngle) % numSectors;
            const sectorLetter = String.fromCharCode(65 + sectorIndex);
            
            return sectorLetter + ring;
        }}
        
        // Wait for DOM to be ready before accessing elements
        function initCoordinateTracking() {{
            // Get the SVG element and coordinate display elements
            const svg = document.querySelector('svg');
            const coordGroup = document.getElementById('coord_display_group');
            const coordBg = document.getElementById('coord_bg');
            const graphicValueText = document.getElementById('coord_graphic_value');
            const galacticValueText = document.getElementById('coord_galactic_value');
            const sectorValueText = document.getElementById('coord_sector_value');
            
            // Check if all elements exist - gracefully handle missing elements
            if (!svg) {{
                console.warn('SVG element not found for coordinate tracking');
                return;
            }}
            
            if (!coordGroup || !coordBg || !graphicValueText || !galacticValueText || !sectorValueText) {{
                console.warn('Coordinate tracking elements not fully available - some features disabled');
                return;
            }}
            
            let offset = {{ x: 15, y: 15 }}; // Offset from cursor
            let lastClientX = 0, lastClientY = 0;

            const bgWidth = parseFloat(coordBg.getAttribute('width'));
            const bgHeight = parseFloat(coordBg.getAttribute('height'));

            function clientToSVG(clientX, clientY) {{
                const rect = svg.getBoundingClientRect();
                if (!rect.width) {{ return null; }}
                return {{
                    x: (clientX - rect.left) * ({self.width}  / rect.width),
                    y: (clientY - rect.top)  * ({self.height} / rect.height)
                }};
            }}

            function placeCoordBox(clientX, clientY) {{
                const svgP = clientToSVG(clientX, clientY);
                if (!svgP) {{ return; }}
                let displayX = svgP.x + offset.x;
                let displayY = svgP.y + offset.y;
                if (displayX + bgWidth > {self.width}) {{
                    displayX = svgP.x - bgWidth - offset.x;
                }}
                if (displayY + bgHeight > {self.height}) {{
                    displayY = svgP.y - bgHeight - offset.y;
                }}
                coordGroup.setAttribute('transform', `translate(${{displayX}}, ${{displayY}})`);
            }}

            svg.addEventListener('mousemove', function(event) {{
                try {{
                    lastClientX = event.clientX;
                    lastClientY = event.clientY;

                    const svgP = clientToSVG(event.clientX, event.clientY);
                    if (!svgP) {{ return; }}

                    // Update coordinate display
                    const galactic = graphicToGalactic(svgP.x, svgP.y);
                    const sector = assignSector(svgP.x, svgP.y);

                    graphicValueText.textContent = `(${{Math.round(svgP.x)}}, ${{Math.round(svgP.y)}})`;
                    galacticValueText.textContent = `(${{Math.round(galactic.x)}}, ${{Math.round(galactic.y)}})`;
                    sectorValueText.textContent = sector || 'Out of bounds';

                    placeCoordBox(event.clientX, event.clientY);
                    coordGroup.setAttribute('opacity', '1');
                }} catch (e) {{
                    console.debug('Error in mousemove handler:', e);
                }}
            }});

            svg.addEventListener('mouseleave', function() {{
                coordGroup.setAttribute('opacity', '0');
            }});

            // Reposition the coord box after scroll/zoom so it tracks the cursor.
            // getScreenCTM() updates after layout; requestAnimationFrame defers until then.
            function onScrollOrZoom() {{
                if (coordGroup.getAttribute('opacity') === '0') {{ return; }}
                requestAnimationFrame(function() {{
                    placeCoordBox(lastClientX, lastClientY);
                }});
            }}
            window.addEventListener('scroll', onScrollOrZoom, true);
            document.addEventListener('scroll', onScrollOrZoom, true);
            window.addEventListener('wheel', onScrollOrZoom, {{ passive: true, capture: true }});
        }}
        
        // Initialize when DOM is ready
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initCoordinateTracking);
        }} else {{
            // DOM is already ready
            initCoordinateTracking();
        }}
        
        // Initialize star hover effects
        function initStarHoverEffects() {{
            const hoverAreas = document.querySelectorAll('.star-hover-area');
            
            hoverAreas.forEach(area => {{
                const targetId = area.getAttribute('data-target');
                const targetObject = document.getElementById(targetId);
                
                if (targetObject) {{
                    area.addEventListener('mouseenter', function() {{
                        targetObject.classList.add('hover-active');
                    }});
                    
                    area.addEventListener('mouseleave', function() {{
                        targetObject.classList.remove('hover-active');
                    }});
                }}
            }});
        }}
        
        // Initialize star hover effects when DOM is ready
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initStarHoverEffects);
        }} else {{
            initStarHoverEffects();
        }}
        """

        if self.interactive:
            script.text += self._zoom_pan_js()

        self.svg.insert(1, script)

    def _zoom_pan_js(self) -> str:
        """viewBox zoom/pan, ported from the former zoom_and_pan script.

        That script also carried ~86 lines of CSS for a #zoom-control panel,
        a #zoom-level-display readout and a #help-toggle, plus a
        create_zoom_controls() method — none of which were ever wired up: the
        method was never called and the styled elements were never created.
        Only the working part is kept here.  The display update below stays
        guarded, so adding that chrome later needs no change to this JS.
        """
        return f"""
        // Zoom & Pan functionality
        let zoomLevel = 1;
        let panX = 0;
        let panY = 0;
        const minZoom = 0.5;
        const maxZoom = 5;
        const zoomStep = 0.1;
        const initialViewBox = '0 0 {self.width} {self.height}';
        
        function updateViewBox() {{
            const svg = document.querySelector('svg');
            const width = {self.width};
            const height = {self.height};
            
            const viewBoxWidth = width / zoomLevel;
            const viewBoxHeight = height / zoomLevel;
            
            // Constrain pan to prevent viewing empty space
            const maxPanX = width - viewBoxWidth;
            const maxPanY = height - viewBoxHeight;
            
            panX = Math.max(0, Math.min(panX, maxPanX));
            panY = Math.max(0, Math.min(panY, maxPanY));
            
            svg.setAttribute('viewBox', `${{panX}} ${{panY}} ${{viewBoxWidth}} ${{viewBoxHeight}}`);
            
            // Update zoom level display
            const zoomDisplay = document.getElementById('zoom-level-display');
            if (zoomDisplay) {{
                zoomDisplay.textContent = (zoomLevel * 100).toFixed(0) + '%';
            }}
        }}
        
        function initZoomPan() {{
            const svg = document.querySelector('svg');
            if (!svg) return;
            
            let isPanning = false;
            let panStartX = 0;
            let panStartY = 0;
            
            // Mouse wheel zoom
            svg.addEventListener('wheel', function(event) {{
                event.preventDefault();
                
                const oldZoom = zoomLevel;
                const direction = event.deltaY > 0 ? -1 : 1;
                zoomLevel += direction * zoomStep;
                zoomLevel = Math.max(minZoom, Math.min(zoomLevel, maxZoom));
                
                // Zoom towards mouse position
                if (oldZoom !== zoomLevel) {{
                    const rect = svg.getBoundingClientRect();
                    const mouseX = event.clientX - rect.left;
                    const mouseY = event.clientY - rect.top;
                    
                    const oldViewBoxWidth = {self.width} / oldZoom;
                    const newViewBoxWidth = {self.width} / zoomLevel;
                    const viewBoxHeight = {self.height} / zoomLevel;
                    const zoomFactor = oldViewBoxWidth / newViewBoxWidth;
                    
                    // Adjust pan to zoom towards mouse
                    panX += (mouseX / rect.width) * ({self.width} / oldZoom) - (mouseX / rect.width) * newViewBoxWidth;
                    panY += (mouseY / rect.height) * ({self.height} / oldZoom) - (mouseY / rect.height) * viewBoxHeight;
                    
                    updateViewBox();
                }}
            }}, {{ passive: false }});
            
            // Pan on left mouse button drag (primary method)
            // or middle mouse button (button 1) drag
            svg.addEventListener('mousedown', function(event) {{
                // Left click (0) or middle click (1) for panning
                if (event.button === 0 || event.button === 1) {{
                    isPanning = true;
                    panStartX = event.clientX;
                    panStartY = event.clientY;
                    svg.style.cursor = 'grabbing';
                    event.preventDefault();
                }}
            }});
            
            svg.addEventListener('mousemove', function(event) {{
                if (isPanning) {{
                    const dx = event.clientX - panStartX;
                    const dy = event.clientY - panStartY;
                    
                    const rect = svg.getBoundingClientRect();
                    const viewBoxWidth = {self.width} / zoomLevel;
                    const viewBoxHeight = {self.height} / zoomLevel;
                    
                    panX -= (dx / rect.width) * viewBoxWidth;
                    panY -= (dy / rect.height) * viewBoxHeight;
                    
                    panStartX = event.clientX;
                    panStartY = event.clientY;
                    
                    updateViewBox();
                }}
            }});
            
            svg.addEventListener('mouseup', function() {{
                isPanning = false;
                svg.style.cursor = 'default';
            }});
            
            svg.addEventListener('mouseleave', function() {{
                isPanning = false;
                svg.style.cursor = 'default';
            }});
            
            // Keyboard controls
            document.addEventListener('keydown', function(event) {{
                const panAmount = {self.width} / zoomLevel / 10;
                
                switch(event.key) {{
                    case '+':
                    case '=':
                        event.preventDefault();
                        zoomLevel = Math.min(zoomLevel + zoomStep, maxZoom);
                        updateViewBox();
                        break;
                    case '-':
                    case '_':
                        event.preventDefault();
                        zoomLevel = Math.max(zoomLevel - zoomStep, minZoom);
                        updateViewBox();
                        break;
                    case 'ArrowUp':
                        event.preventDefault();
                        panY = Math.max(0, panY - panAmount);
                        updateViewBox();
                        break;
                    case 'ArrowDown':
                        event.preventDefault();
                        panY += panAmount;
                        updateViewBox();
                        break;
                    case 'ArrowLeft':
                        event.preventDefault();
                        panX = Math.max(0, panX - panAmount);
                        updateViewBox();
                        break;
                    case 'ArrowRight':
                        event.preventDefault();
                        panX += panAmount;
                        updateViewBox();
                        break;
                    case '0':
                        event.preventDefault();
                        zoomLevel = 1;
                        panX = 0;
                        panY = 0;
                        updateViewBox();
                        break;
                }}
            }});
            
            // Right-click context menu for reset
            svg.addEventListener('contextmenu', function(event) {{
                event.preventDefault();
                // Reset to initial view
                zoomLevel = 1;
                panX = 0;
                panY = 0;
                updateViewBox();
            }});
        }}
        
        // Initialize zoom/pan when DOM is ready
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initZoomPan);
        }} else {{
            initZoomPan();
        }}
        """

    def add_styles(self):
        """Add CSS styles for hover effects and star classifications."""
        style = ET.Element('style', {'type': 'text/css'})
        style.text = """
            /* Mouse coordinate display */
            .coord-display {
                transition: opacity 0.2s ease;
            }
            
            /* Sector hover effects */
            .sector {
                transition: all 0.2s ease;
            }
            .sector-shape {
                cursor: pointer;
                transition: fill 0.2s ease;
            }
            .sector:hover .sector-shape {
                fill: rgba(100, 150, 255, 0.3);
            }
            .sector:hover .sector-hover-label {
                opacity: 1 !important;
            }
            /* Hide permanent sector names on hover to show only hover label */
            .sector:hover .sector-name-permanent {
                opacity: 0;
            }
            
            /* Celestial object styles */
            .celestial-object {
                transition: all 0.2s ease;
            }
            
            .object-dot {
                transition: all 0.2s ease;
            }
            
            .object-glow {
                filter: blur(2px);
            }
            
            /* Black hole specific styles */
            .black-hole-accretion-outer {
                filter: blur(4px);
            }
            
            .black-hole-accretion-middle {
                filter: blur(2px);
            }
            
            .black-hole-accretion-ring {
                filter: blur(0.5px);
            }
            
            .black-hole-core {
                /* Pure black center */
            }
            
            /* Object labels are permanently visible */
            .object-label {
                opacity: 1;
                transition: opacity 0.2s ease;
            }
            
            /* A real star's name shows on hover only. */
            .real-star .object-label {
                opacity: 0 !important;
            }
            .real-star:hover .object-label,
            .real-star.hover-active .object-label {
                opacity: 1 !important;
            }

            .object-type-label {
                opacity: 0.7;
                transition: opacity 0.2s ease;
            }
            
            /* Star hover area (invisible overlay) */
            .star-hover-area {
                cursor: pointer;
                /* Debug: uncomment to see hover areas */
                /* fill: rgba(255, 0, 0, 0.1) !important; */
            }
            
            /* Hover effects for celestial objects */
            .celestial-object:hover .object-dot,
            .celestial-object.hover-active .object-dot {
                filter: brightness(1.5);
                stroke: #ffffff;
                stroke-width: 0.5;
            }
            
            .celestial-object:hover .object-label,
            .celestial-object.hover-active .object-label {
                font-weight: bold;
                font-size: 20px !important;
                opacity: 1 !important;
            }
            
            /* A real star's name, shown on hover, at the largest size a label
               otherwise has: the 20px above is eight times a real star's
               own, crowded as they are round Sol. */
            .celestial-object.real-star:hover .object-label,
            .celestial-object.real-star.hover-active .object-label {
                font-size: 8px !important;
            }

            .celestial-object:hover .object-type-label,
            .celestial-object.hover-active .object-type-label {
                font-size: 5px !important;
                opacity: 1 !important;
            }
            
            .celestial-object:hover .object-glow,
            .celestial-object.hover-active .object-glow {
                opacity: 0.6 !important;
            }
            
            /* Prevent text selection */
            text {
                user-select: none;
                -webkit-user-select: none;
                -moz-user-select: none;
            }
        """
        self.svg.insert(0, style)
    
    def generate(self, data: Dict, output_path: str, territories: Optional[List[Dict]] = None):
        """Generate the complete SVG galaxy map from `data` (galaxy.json) and
        write it to `output_path`, atomically.

        `territories` (galaxy/territories.py, as dicts) adds a layer beneath the
        stars; without it the map is unchanged.
        """
        self.svg = self.create_svg_root()
        
        # Add styles and JavaScript
        self.add_styles()
        self.add_javascript()

        # Create layers in order
        background = self.create_background()
        self.svg.append(background)
        
        # Support both 'galaxy_labels' and 'labels' for backward compatibility
        labels_data = data.get('galaxy_labels', data.get('labels', []))
        labels = self.create_labels(labels_data)
        self.svg.append(labels)
        
        grid = self.create_grid()
        self.svg.append(grid)
        
        # Add legend
        legend = self.create_legend()
        self.svg.append(legend)

        # Add mouse coordinate display
        mouse_coords = self.create_mouse_coordinates_display()
        self.svg.append(mouse_coords)

        if territories:
            self.svg.append(self.create_territories(territories))

        # Nebulae: regions under the stars.
        if data.get('nebulae'):
            self.svg.append(self.create_nebulae(data['nebulae']))

        sector_names = data.get('sector_names', {})
        sectors = self.create_sectors(sector_names)
        self.svg.append(sectors)
        
        # Add celestial objects (support both 'celestial_objects' and 'star_systems' for backward compatibility)
        celestial_objects = data.get('celestial_objects', data.get('star_systems', []))
        self.add_celestial_objects(sectors, celestial_objects)

        # Now add all sector shapes at the END so they're below stars in z-order
        self._add_sector_shapes(sectors)

        # Add star hover overlay layer on top of everything
        star_hover_overlay = self.create_star_hover_overlay()
        self.svg.append(star_hover_overlay)

        # Serialised in memory and written once, through a temporary file: the
        # published map is read while a Save regenerates it.
        tree = ET.ElementTree(self.svg)
        ET.indent(tree, space='  ')
        content = ET.tostring(self.svg, encoding='unicode', xml_declaration=True)
        write_atomic(output_path, self._fix_duplicate_namespaces(content))

        print(f"Galaxy map generated: {output_path}")

    def _fix_duplicate_namespaces(self, content: str) -> str:
        """Remove duplicate namespace declarations from the SVG text."""

        # Fix duplicate xmlns:inkscape declarations
        def replace_duplicates(match):
            line = match.group(0)
            # Split by space and filter
            parts = []
            seen_inkscape_ns = False
            for part in line.split():
                if 'xmlns:inkscape=' in part:
                    if not seen_inkscape_ns:
                        parts.append(part)
                        seen_inkscape_ns = True
                else:
                    parts.append(part)
            return ' '.join(parts)

        return re.sub(r'<svg[^>]+>', replace_duplicates, content)

