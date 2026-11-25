# Celestial Objects Documentation

## Overview

The Galaxy Map Generator now supports a comprehensive system for rendering both stars and special celestial objects like black holes, neutron stars, pulsars, and more.

## JSON Schema

### Field Structure

```json
{
  "galaxy_labels": [...],
  "sector_names": {...},
  "celestial_objects": [
    {
      "name": "Object Name",
      "object_type": "star",
      "spectral_class": "G2V",
      "x": 2800,
      "y": 2800,
      "coordinate_system": "graphic"
    }
  ]
}
```

### Fields

#### `object_type` (optional, defaults to "star")
Specifies the type of celestial object:
- `"star"` - Regular star (default)
- `"black_hole"` - Black hole with accretion disk
- `"neutron_star"` - Neutron star
- `"pulsar"` - Pulsar (rotating neutron star)
- `"white_dwarf"` - White dwarf
- `"wormhole"` - Wormhole
- `"anomaly"` - Unknown spatial anomaly
- `"nebula"` - Nebula/gas cloud
- `"quasar"` - Quasar

#### `spectral_class` (optional, used when object_type="star")
Morgan-Keenan stellar classification:
- Main classes: `O`, `B`, `A`, `F`, `G`, `K`, `M`
- Detailed: `G2V`, `M5III`, etc.
- If omitted, renders as white/unclassified

#### `name` (required)
Display name of the object

#### `x`, `y`, `z` (required)
Coordinates (z is optional)

#### `coordinate_system` (optional, defaults to "graphic")
- `"graphic"` - SVG coordinates
- `"galactic"` - Galactic coordinate system (will be converted)

## Supported Object Types

### Stars (Morgan-Keenan Classification)

| Class | Color | Temperature | Size | Description |
|-------|-------|-------------|------|-------------|
| **O** | Blue (#9bb0ff) | 30,000+ K | 2.5× | Extremely hot and luminous |
| **B** | Blue-white (#aabfff) | 10,000-30,000 K | 2.0× | Hot and luminous |
| **A** | White (#cad7ff) | 7,500-10,000 K | 1.8× | Strong hydrogen lines |
| **F** | Yellow-white (#f8f7ff) | 6,000-7,500 K | 1.5× | Yellow-white stars |
| **G** | Yellow (#fff4ea) | 5,200-6,000 K | 1.2× | Like our Sun |
| **K** | Orange (#ffd2a1) | 3,700-5,200 K | 1.0× | Cooler main sequence |
| **M** | Red (#ffcc6f) | <3,700 K | 0.8× | Coolest and most common |

### Special Objects

| Type | Color | Size | Visual Effect | Description |
|------|-------|------|---------------|-------------|
| **black_hole** | Black core with orange glow | 2.0× | Multi-layered accretion disk | Black hole with glowing accretion disk |
| **neutron_star** | Cyan (#00ffff) | 1.5× | Bright glow | Extremely dense collapsed star |
| **pulsar** | Green (#00ff00) | 1.5× | Bright glow | Rotating neutron star |
| **white_dwarf** | Pale blue (#e0e0ff) | 1.0× | Simple dot | Dense stellar remnant |
| **wormhole** | Purple (#9400d3) | 4.0× | Large dot | Theoretical spacetime tunnel |
| **anomaly** | Magenta (#ff00ff) | 2.5× | Medium dot | Unknown spatial phenomenon |
| **nebula** | Hot pink (#ff69b4) | 8.0× | Very large | Interstellar gas cloud |
| **quasar** | Bright yellow (#ffff00) | 3.5× | Bright glow | Extremely luminous AGN |

## Visual Details

### Black Hole Rendering

Black holes have a special multi-layered rendering:
1. **Outer accretion disk** - Large, diffuse orange glow (blurred)
2. **Middle disk** - Medium, brighter orange layer
3. **Inner ring** - Thin bright orange ring
4. **Core** - Pure black center with orange outline

This creates a realistic accretion disk effect around the event horizon.

### Glow Effects

Objects with `has_glow: True` receive an additional blur effect:
- O, B, A class stars
- Neutron stars
- Pulsars
- Quasars

## JSON Examples

### Basic Star
```json
{
  "name": "Sol",
  "spectral_class": "G2V",
  "x": 2800,
  "y": 2800
}
```

### Black Hole
```json
{
  "name": "Cygnus X-1",
  "object_type": "black_hole",
  "x": 3700,
  "y": 2300
}
```

### Pulsar
```json
{
  "name": "PSR B1919+21",
  "object_type": "pulsar",
  "x": 3800,
  "y": 2200
}
```

### Nebula
```json
{
  "name": "Orion Nebula",
  "object_type": "nebula",
  "x": 4000,
  "y": 2000
}
```

### Complete Example
```json
{
  "galaxy_labels": [
    {
      "label": "Core Worlds",
      "x": 3000,
      "y": 3000,
      "rotation": 0
    }
  ],
  "sector_names": {
    "0": "Galactic Core",
    "A1": "Alpha Sector"
  },
  "celestial_objects": [
    {
      "name": "Sol",
      "object_type": "star",
      "spectral_class": "G2V",
      "x": 2800,
      "y": 2800
    },
    {
      "name": "Cygnus X-1",
      "object_type": "black_hole",
      "x": 3700,
      "y": 2300
    },
    {
      "name": "Vega",
      "object_type": "star",
      "spectral_class": "A",
      "x": 2900,
      "y": 2750
    },
    {
      "name": "Unknown Anomaly",
      "object_type": "anomaly",
      "x": 4100,
      "y": 1900
    }
  ]
}
```

## Backward Compatibility

The system maintains backward compatibility:

### Old Format Still Supported
```json
{
  "labels": [...],
  "star_systems": [
    {
      "name": "Sol",
      "type": "G2V",
      "x": 2800,
      "y": 2800
    }
  ]
}
```

This will be automatically converted to:
- `labels` → `galaxy_labels`
- `star_systems` → `celestial_objects`
- `type` → treated as `spectral_class` with `object_type` defaulting to "star"

### Migration Path

To migrate old JSON files:
1. Rename `"labels"` → `"galaxy_labels"`
2. Rename `"star_systems"` → `"celestial_objects"`
3. For each object:
   - Add `"object_type": "star"` (optional, it's the default)
   - Rename `"type"` → `"spectral_class"`
4. Add special objects with appropriate `object_type`

## CSS Classes

Objects are assigned CSS classes for styling:
- `.celestial-object` - All objects
- `.star`, `.black_hole`, `.pulsar`, etc. - Specific type classes
- `.object-dot` - The main visual element
- `.object-glow` - Glow effect layer
- `.black-hole-accretion-outer/middle/ring/core` - Black hole layers
- `.object-label` - Object name label
- `.object-type-label` - Type description label

## Hover Effects

All celestial objects have hover effects:
- Brightness increase on the dot
- Bold label text
- White outline
- Intensified glow (if applicable)

## Future Enhancements

Potential additions:
- Binary star systems (multiple objects at same location)
- Animated pulsars (blinking effect)
- Animated wormholes (rotating spiral)
- Custom icons for anomalies
- Nebula with irregular shapes
- Constellation lines
- Planet systems around stars
- Distance indicators
- Jump routes between objects

## Technical Notes

### Rendering Order (Z-Index)
1. Background
2. Galaxy labels
3. Grid
4. Legend
5. Sectors
6. Sector shapes (drawn first within sector)
7. Celestial objects (drawn last, on top)

### Performance
- Large nebulae (8.0× radius) may overlap multiple sectors
- Black hole accretion disks use blur filters (may be GPU intensive)
- Recommend limiting to <1000 objects per map for optimal performance

## Examples in the Wild

See `example_data.json` for a complete working example with:
- 7 different star types (O, B, A, F, G, K, M)
- 1 unclassified star
- 1 black hole (Cygnus X-1)
- 2 neutron stars (one regular, one pulsar)
- 1 white dwarf (Sirius B)
- 1 nebula (Orion Nebula)
- 1 anomaly
- 1 quasar (3C 273)
- 1 wormhole

## Command Line Usage

```bash
# Generate map with all object types
python3 generate_galaxy_map.py \
  --input example_data.json \
  --output galaxy_map.svg \
  --width 5600 \
  --height 5600
```

## SVG Output

The generated SVG includes:
- Proper Inkscape layers for organization
- CSS animations and transitions
- Hover effects
- Selectable/editable in vector graphics software
- Scalable to any size without quality loss
- Web-ready with interactive features
