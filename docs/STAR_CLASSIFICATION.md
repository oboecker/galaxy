# Star Classification System

## Overview

The Galaxy Map Generator now supports the Morgan-Keenan (MK) stellar classification system, allowing stars to be displayed with scientifically accurate colors, sizes, and properties.

## Supported Star Classes

| Class | Color | Temperature | Description | Display Size |
|-------|-------|-------------|-------------|--------------|
| **O** | Blue (#9bb0ff) | 30,000+ K | Extremely hot and luminous | 2.5× |
| **B** | Blue-white (#aabfff) | 10,000-30,000 K | Hot and luminous | 2.0× |
| **A** | White (#cad7ff) | 7,500-10,000 K | Strong hydrogen lines | 1.8× |
| **F** | Yellow-white (#f8f7ff) | 6,000-7,500 K | Yellow-white stars | 1.5× |
| **G** | Yellow (#fff4ea) | 5,200-6,000 K | Like our Sun | 1.2× |
| **K** | Orange (#ffd2a1) | 3,700-5,200 K | Cooler main sequence | 1.0× |
| **M** | Red (#ffcc6f) | <3,700 K | Coolest and most common | 0.8× |

## JSON Format

### Basic Star (No Classification)
```json
{
  "name": "Unknown Star",
  "x": 3000,
  "y": 2800,
  "coordinate_system": "graphic"
}
```
- Will render as white, default size (1.0)

### Classified Star (Simple)
```json
{
  "name": "Proxima Centauri",
  "x": 3200,
  "y": 2800,
  "coordinate_system": "graphic",
  "type": "M"
}
```
- Will render as red dwarf with appropriate color and size

### Classified Star (Detailed)
```json
{
  "name": "Sol",
  "x": -513,
  "y": 24995,
  "z": 50,
  "coordinate_system": "galactic",
  "type": "G2V",
  "comment": "Our home star - yellow dwarf"
}
```
- The script uses only the first letter ('G') for classification
- Full spectral type (e.g., 'G2V') is displayed on the map
- `comment` field is optional and not displayed (for documentation)

## Visual Features

### Star Appearance
1. **Color**: Each star class has a scientifically accurate color
2. **Size**: Stars are sized relative to their classification:
   - O, B, A stars are larger (hot, luminous)
   - K, M stars are smaller (cool, dim)
3. **Glow Effect**: O, B, and A class stars get a subtle glow effect to represent their luminosity

### Labels
- **Star Name**: Always visible, colored to match the star
- **Star Type**: Displayed below the name in parentheses (e.g., "(G2V)")
- **Label Position**: Automatically offset based on star size

### Hover Effects
When hovering over a star:
- Star brightness increases (150%)
- Label becomes bold
- Type label becomes fully opaque
- Glow effect intensifies (for O, B, A stars)

## Legend

A legend is automatically added to the top-right corner of the map showing:
- All seven star classes with example dots
- Color and temperature for each class
- Visual reference for unclassified stars

## Examples

### Complete Example
See `example_data.json` for a full example including:
- Sol (G2V) - yellow star like our Sun
- Alpha Centauri A (G) - similar to Sol
- Proxima Centauri (M) - red dwarf
- Sirius A (A) - white star
- Betelgeuse (M) - red supergiant
- Rigel (B) - blue supergiant
- Unknown Star (unclassified) - default white

### Real-World Usage
```bash
# Generate map with star classifications
python3 generate_galaxy_map.py \
  --input example_data.json \
  --output galaxy_map_with_stars.svg \
  --width 5600 \
  --height 5600
```

## Technical Details

### StarClassification Class
The `StarClassification` class handles all star properties:
```python
# Get properties for a star type
props = StarClassification.get_star_properties('G')
# Returns: {'color': '#fff4ea', 'temperature': '5,200-6,000 K', 
#           'radius': 1.2, 'description': 'Yellow, like Sol'}

# Get just the color
color = StarClassification.get_color('M')  # Returns '#ffcc6f'

# Get display radius
radius = StarClassification.get_radius('B', base_radius=1.0)  # Returns 2.0
```

### SVG Structure
Each star is rendered as:
```xml
<g class="star" data-star-type="G2V">
  <!-- Optional glow for bright stars -->
  <circle class="star-glow" ... />
  
  <!-- Main star dot -->
  <circle class="star-dot" ... />
  
  <!-- Star name -->
  <text class="star-label">Sol</text>
  
  <!-- Star classification -->
  <text class="star-type-label">(G2V)</text>
</g>
```

### CSS Classes
- `.star` - Star group container
- `.star-dot` - The star circle
- `.star-glow` - Glow effect (O, B, A stars only)
- `.star-label` - Star name text
- `.star-type-label` - Star classification text

## Future Enhancements

Potential additions:
- Luminosity classes (V, IV, III, II, I, 0)
- Binary/multiple star systems
- Variable stars with animation
- Special objects (neutron stars, black holes, white dwarfs)
- Constellation lines connecting stars
- Filter by star type (show/hide classes)
- Search and highlight by classification

## Scientific Notes

The Morgan-Keenan system is the most widely used stellar classification system:
- **Primary classification**: Based on surface temperature
- **Order**: OBAFGKM (mnemonic: "Oh Be A Fine Girl/Guy, Kiss Me")
- **Additional notation**: 
  - Numbers 0-9 for subdivisions (e.g., G2)
  - Luminosity class (e.g., V for main sequence, III for giant)

Our implementation uses the primary letter for color/size, but displays the full classification string for accuracy.
