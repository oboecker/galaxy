# Galaxy Map SVG Generator

A Python script that generates an SVG image of a galaxy map with sectors, grid, labels, stars, and special celestial objects like black holes, neutron stars, pulsars, and more.

## Features

### Core Features
- Configurable image size (default 5600×5600)
- Inkscape-compatible SVG with proper layers and IDs
- Grid system with:
  - Central circle (radius 150)
  - 15 concentric rings (150 units wide each)
  - 24 radial beams (15° apart, labeled A-X)
- 361 sector layers (24×15 + center) with optional names
- Support for both galactic and graphic coordinate systems
- Interactive hover effects
- Galactic location labels

### Celestial Objects
- **Stars**: Full Morgan-Keenan classification (O, B, A, F, G, K, M)
  - Color-coded by spectral class
  - Size scaling based on temperature
  - Glow effects for hot stars
- **Black Holes**: Multi-layered accretion disk rendering
- **Neutron Stars & Pulsars**: Bright cyan/green with glow
- **White Dwarfs**: Compact stellar remnants
- **Nebulae**: Large gas clouds
- **Wormholes**: Theoretical spacetime tunnels
- **Anomalies**: Unknown phenomena
- **Quasars**: Extremely luminous objects

## Usage

```bash
./generate_galaxy_map.py -i <input.json> -o <output.svg> [--width WIDTH] [--height HEIGHT]
```

### Arguments

- `-i, --input`: Input JSON file (required)
- `-o, --output`: Output SVG file (required)
- `-w, --width`: Image width in pixels (default: 6000)
- `--height`: Image height in pixels (default: 6000)

### Example

```bash
./generate_galaxy_map.py -i example_data.json -o galaxy_map.svg
```

Or with custom size:

```bash
./generate_galaxy_map.py -i data.json -o map.svg --width 8000 --height 8000
```

## Input JSON Format

The input JSON file should contain the following fields:

### Galaxy Labels

Galactic location labels that appear on the map:

```json
{
  "galaxy_labels": [
    {
      "label": "Core Worlds",
      "x": 3000,
      "y": 3000,
      "rotation": 0
    }
  ]
}
```

**Note**: The old field name `labels` is still supported for backward compatibility.

- `label`: Text to display
- `x`, `y`: Coordinates for label placement
- `rotation`: (optional) Rotation angle in degrees

### Sector Names

Named sectors that are always visible:

```json
{
  "sector_names": {
    "0": "Galactic Core",
    "A1": "Alpha Sector",
    "X7": "Proxima Sector"
  }
}
```

- Key: Sector ID (e.g., "A1", "B3", "0" for center)
- Value: Sector name

### Celestial Objects

Stars and special objects to be plotted on the map:

```json
{
  "celestial_objects": [
    {
      "name": "Sol",
      "object_type": "star",
      "spectral_class": "G2V",
      "x": -513,
      "y": 24995,
      "z": 50,
      "coordinate_system": "galactic"
    },
    {
      "name": "Alpha Centauri",
      "spectral_class": "G",
      "x": 3100,
      "y": 2900,
      "coordinate_system": "graphic"
    },
    {
      "name": "Cygnus X-1",
      "object_type": "black_hole",
      "x": 3700,
      "y": 2300
    },
    {
      "name": "Orion Nebula",
      "object_type": "nebula",
      "x": 4000,
      "y": 2000
    }
  ]
}
```

#### Fields
- `name`: Object name (required)
- `object_type`: Type of object (optional, defaults to "star")
  - `"star"`, `"black_hole"`, `"neutron_star"`, `"pulsar"`, `"white_dwarf"`, `"wormhole"`, `"anomaly"`, `"nebula"`, `"quasar"`
- `spectral_class`: Star classification (optional, only for stars)
  - Main classes: `"O"`, `"B"`, `"A"`, `"F"`, `"G"`, `"K"`, `"M"`
  - Detailed: `"G2V"`, `"M5III"`, etc.
- `x`, `y`, `z`: Coordinates (z is optional and only used for galactic coordinates)
- `coordinate_system`: Either `"galactic"` or `"graphic"` (default: `"graphic"`)

**Note**: The old field name `star_systems` with `type` field is still supported for backward compatibility.

## Coordinate Systems

The script supports two coordinate systems:

1. **Galactic Coordinates**: Fictional coordinate system that gets converted to graphic coordinates
   - Uses Sol as reference point: galactic (-513, 24995, 50) = graphic (scaled to image size)
   - Z-coordinate is accepted but not used in conversion

2. **Graphic Coordinates**: Direct SVG/image coordinates
   - Origin at top-left (0, 0)
   - Center of galaxy at (width/2, height/2)

## Grid System

The galaxy is divided into sectors using:

- **Center Circle**: Sector "0" with radius 150
- **Rings**: 15 rings numbered 1-15, each 150 units wide
- **Radial Beams**: 24 beams labeled A-X, spaced 15° apart
  - A starts at the top (0°)
  - Letters proceed counter-clockwise
  
This creates 361 total sectors (24×15 + 1 center).

## SVG Structure

The generated SVG contains the following layers (bottom to top):

1. **Background**: Dark background rectangle
2. **Labels**: Galactic location labels (56px, #4d4d4d)
3. **Grid**: Center circle, rings (with numbers), and radial beams (with letters)
4. **Sectors**: Individual sector layers with optional names and star systems
   - Each sector is a sub-layer
   - Star systems appear within their respective sector layer
   - Hover effects show star names

## Font

All text uses **"Lithos Pro Regular"** font family. Ensure this font is installed for proper rendering in Inkscape.

## Integration with Existing Scripts

This script integrates the logic from:

- `sector_assignment.py`: Sector assignment based on polar coordinates
- `conversion.js`: Coordinate conversion between galactic and graphic systems

The coordinate conversion and sector assignment automatically scale to the configured image size.

## Documentation

For detailed information, see:
- **[CELESTIAL_OBJECTS.md](CELESTIAL_OBJECTS.md)** - Complete guide to all object types
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Quick examples and snippets
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and changes
- **[STAR_CLASSIFICATION.md](STAR_CLASSIFICATION.md)** - Stellar classification details

## Examples

See `example_data.json` for a complete example including:
- 7 different star types (O, B, A, F, G, K, M)
- 1 unclassified star
- 1 black hole with accretion disk
- 1 pulsar
- 1 neutron star
- 1 white dwarf
- 1 nebula
- 1 anomaly
- 1 quasar
- 1 wormhole

## Visual Examples

### Black Holes
Black holes feature a unique multi-layered rendering:
- Pure black core
- Bright inner ring
- Glowing middle accretion disk
- Diffuse outer glow
- Orange-red coloring (#ff4500)

### Stars
Stars are color-coded by temperature:
- **O** (Blue) - Hottest
- **B** (Blue-white) - Very hot
- **A** (White) - Hot
- **F** (Yellow-white) - Warm
- **G** (Yellow) - Like our Sun
- **K** (Orange) - Cool
- **M** (Red) - Coolest

### Interactive Features
- Hover over any object to see enhanced brightness
- Sector highlighting on hover
- Permanently visible labels for all objects
- Type descriptions for special objects

## Backward Compatibility

The script maintains full backward compatibility:
- Old `labels` field → automatically converted to `galaxy_labels`
- Old `star_systems` field → automatically converted to `celestial_objects`
- Old `type` field → treated as `spectral_class` for stars
- Existing JSON files work without modification
