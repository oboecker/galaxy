# Quick Reference Guide

## Adding Objects to Your Galaxy Map

### Regular Star
```json
{
  "name": "Star Name",
  "spectral_class": "G",
  "x": 2800,
  "y": 2800
}
```

### Black Hole
```json
{
  "name": "Black Hole Name",
  "object_type": "black_hole",
  "x": 3700,
  "y": 2300
}
```

### Neutron Star
```json
{
  "name": "Neutron Star Name",
  "object_type": "neutron_star",
  "x": 3900,
  "y": 2100
}
```

### Pulsar
```json
{
  "name": "Pulsar Name",
  "object_type": "pulsar",
  "x": 3800,
  "y": 2200
}
```

### White Dwarf
```json
{
  "name": "White Dwarf Name",
  "object_type": "white_dwarf",
  "x": 3330,
  "y": 2720
}
```

### Nebula
```json
{
  "name": "Nebula Name",
  "object_type": "nebula",
  "x": 4000,
  "y": 2000
}
```

### Wormhole
```json
{
  "name": "Wormhole Name",
  "object_type": "wormhole",
  "x": 4300,
  "y": 1700
}
```

### Anomaly
```json
{
  "name": "Anomaly Name",
  "object_type": "anomaly",
  "x": 4100,
  "y": 1900
}
```

### Quasar
```json
{
  "name": "Quasar Name",
  "object_type": "quasar",
  "x": 4200,
  "y": 1800
}
```

## Spectral Classes (for Stars)

- **O** - Blue, hottest (30,000+ K)
- **B** - Blue-white, very hot
- **A** - White, hot
- **F** - Yellow-white, warm
- **G** - Yellow, like our Sun
- **K** - Orange, cool
- **M** - Red, coolest

## Object Types Quick Reference

| Type | Code | Color | Size | Glow |
|------|------|-------|------|------|
| Star (O) | `spectral_class: "O"` | Blue | 2.5× | Yes |
| Star (G) | `spectral_class: "G"` | Yellow | 1.2× | No |
| Star (M) | `spectral_class: "M"` | Red | 0.8× | No |
| Black Hole | `object_type: "black_hole"` | Black + Orange | 2.0× | Disk |
| Neutron Star | `object_type: "neutron_star"` | Cyan | 1.5× | Yes |
| Pulsar | `object_type: "pulsar"` | Green | 1.5× | Yes |
| White Dwarf | `object_type: "white_dwarf"` | Pale Blue | 1.0× | No |
| Wormhole | `object_type: "wormhole"` | Purple | 4.0× | No |
| Anomaly | `object_type: "anomaly"` | Magenta | 2.5× | No |
| Nebula | `object_type: "nebula"` | Hot Pink | 8.0× | No |
| Quasar | `object_type: "quasar"` | Yellow | 3.5× | Yes |

## Coordinate Systems

### Graphic Coordinates (Default)
```json
{
  "x": 2800,
  "y": 2800,
  "coordinate_system": "graphic"
}
```

### Galactic Coordinates
```json
{
  "x": -513,
  "y": 24995,
  "z": 50,
  "coordinate_system": "galactic"
}
```

## Complete Example

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
    "A1": "Alpha Quadrant"
  },
  "celestial_objects": [
    {
      "name": "Sol",
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
      "name": "Orion Nebula",
      "object_type": "nebula",
      "x": 4000,
      "y": 2000
    }
  ]
}
```

## Command Line

```bash
# Generate map
python3 generate_galaxy_map.py \
  --input my_galaxy.json \
  --output my_galaxy.svg \
  --width 5600 \
  --height 5600
```

## Tips

1. **Object Type**: If omitted, defaults to "star"
2. **Spectral Class**: Only needed for stars
3. **Coordinates**: Most objects use graphic coordinates
4. **Size**: Larger objects (nebulae, wormholes) may overlap sectors
5. **Colors**: Labels match object colors automatically
6. **Black Holes**: Get special accretion disk rendering
7. **Unclassified**: Stars without spectral_class render white

## Common Patterns

### Solar System Equivalent
```json
{
  "name": "Central Star",
  "spectral_class": "G",
  "x": 2800,
  "y": 2800
}
```

### Binary Black Hole System
```json
[
  {
    "name": "Black Hole A",
    "object_type": "black_hole",
    "x": 3700,
    "y": 2300
  },
  {
    "name": "Black Hole B",
    "object_type": "black_hole",
    "x": 3710,
    "y": 2310
  }
]
```

### Star Forming Region
```json
[
  {
    "name": "Formation Nebula",
    "object_type": "nebula",
    "x": 4000,
    "y": 2000
  },
  {
    "name": "Young Star 1",
    "spectral_class": "O",
    "x": 4005,
    "y": 2005
  },
  {
    "name": "Young Star 2",
    "spectral_class": "B",
    "x": 4010,
    "y": 2000
  }
]
```

## Troubleshooting

**Object not appearing?**
- Check coordinates are within bounds (0-5600 for default size)
- Verify JSON syntax is correct
- Check object_type spelling

**Wrong color?**
- For stars: check spectral_class spelling (O, B, A, F, G, K, M)
- For special objects: check object_type spelling

**Label hard to read?**
- Black holes automatically use orange labels
- Other objects use their primary color
- Consider object placement away from grid lines
