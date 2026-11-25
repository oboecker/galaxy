"""Celestial object appearance: spectral classes and special object types."""
from typing import Dict, Optional


class CelestialObjectClassification:
    """Handles all celestial object properties (stars and special objects)."""
    # Spectral classification for stars (Morgan-Keenan system)
    SPECTRAL_CLASSES = {
        'O': {
            'color': '#9bb0ff',
            'temperature': '30,000+ K',
            'radius': 1.25,
            'description': 'Blue, extremely hot and luminous',
            'icon': 'star',
            'has_glow': True
        },
        'B': {
            'color': '#aabfff',
            'temperature': '10,000-30,000 K',
            'radius': 1.0,
            'description': 'Blue-white, hot and luminous',
            'icon': 'star',
            'has_glow': True
        },
        'A': {
            'color': '#cad7ff',
            'temperature': '7,500-10,000 K',
            'radius': 0.9,
            'description': 'White, strong hydrogen lines',
            'icon': 'star',
            'has_glow': True
        },
        'F': {
            'color': '#f8f7ff',
            'temperature': '6,000-7,500 K',
            'radius': 0.75,
            'description': 'Yellow-white',
            'icon': 'star',
            'has_glow': False
        },
        'G': {
            'color': '#fff4ea',
            'temperature': '5,200-6,000 K',
            'radius': 0.6,
            'description': 'Yellow, like Sol',
            'icon': 'star',
            'has_glow': False
        },
        'K': {
            'color': '#ffd2a1',
            'temperature': '3,700-5,200 K',
            'radius': 0.5,
            'description': 'Orange, cooler main sequence',
            'icon': 'star',
            'has_glow': False
        },
        'M': {
            'color': '#ffcc6f',
            'temperature': '<3,700 K',
            'radius': 0.4,
            'description': 'Red, coolest and most common',
            'icon': 'star',
            'has_glow': False
        },
    }

    # Special celestial objects
    OBJECT_TYPES = {
        'black_hole': {
            'color': '#000000',
            'secondary_color': '#ff4500',
            'temperature': 'N/A',
            'radius': 2.0,
            'description': 'Black Hole',
            'icon': 'accretion_disk',
            'has_glow': False
        },
        'neutron_star': {
            'color': '#00ffff',
            'secondary_color': '#ffffff',
            'temperature': '~10^6 K',
            'radius': 1.5,
            'description': 'Neutron Star',
            'icon': 'glow',
            'has_glow': True
        },
        'pulsar': {
            'color': '#00ff00',
            'secondary_color': '#00ff7f',
            'temperature': '~10^6 K',
            'radius': 1.5,
            'description': 'Pulsar',
            'icon': 'beams',
            'has_glow': True
        },
        'white_dwarf': {
            'color': '#e0e0ff',
            'secondary_color': '#ffffff',
            'temperature': '8,000-16,000 K',
            'radius': 1.0,
            'description': 'White Dwarf',
            'icon': 'simple',
            'has_glow': False
        },
        'wormhole': {
            'color': '#9400d3',
            'secondary_color': '#4b0082',
            'temperature': 'N/A',
            'radius': 4.0,
            'description': 'Wormhole',
            'icon': 'spiral',
            'has_glow': False
        },
        'anomaly': {
            'color': '#ff00ff',
            'secondary_color': '#ff1493',
            'temperature': 'Unknown',
            'radius': 2.5,
            'description': 'Spatial Anomaly',
            'icon': 'diamond',
            'has_glow': False
        },
        'quasar': {
            'color': '#ffff00',
            'secondary_color': '#ffa500',
            'temperature': 'N/A',
            'radius': 3.5,
            'description': 'Quasar',
            'icon': 'rays',
            'has_glow': True
        },
    }

    # Default for unclassified stars
    DEFAULT_STAR = {
        'color': '#ffffff',
        'temperature': 'Unknown',
        'radius': 0.5,
        'description': 'Unclassified',
        'icon': 'star',
        'has_glow': False
    }

    @classmethod
    def get_properties(cls, object_type: str = 'star', spectral_class: Optional[str] = None) -> Dict:
        """How an object looks: color, temperature, radius, description, icon,
        has_glow. A star by its `spectral_class` ('G', or by the letter of 'G2V'),
        DEFAULT_STAR without one; any other `object_type` ('black_hole',
        'quasar', …) by OBJECT_TYPES, a grey unknown for one not listed."""
        if object_type == 'star':
            if spectral_class is None:
                return cls.DEFAULT_STAR

            spectral_upper = spectral_class.upper()
            # Try exact match first (e.g., 'G')
            if spectral_upper in cls.SPECTRAL_CLASSES:
                return cls.SPECTRAL_CLASSES[spectral_upper]

            # Try first letter for detailed classifications (e.g., 'G2V' -> 'G')
            first_letter = spectral_class[0].upper() if spectral_class else None
            return cls.SPECTRAL_CLASSES.get(first_letter, cls.DEFAULT_STAR)
        else:
            # Special object type
            return cls.OBJECT_TYPES.get(object_type, {
                'color': '#808080',
                'temperature': 'Unknown',
                'radius': 2.0,
                'description': 'Unknown Object',
                'icon': 'unknown',
                'has_glow': False
            })

