# Map of the Galaxy

The goal is to create a Python script that creates an SVG image of the galaxy including a sector grid, labels, and star
systems.

In general, the image should be:

- have a configurable size, but use a default of 6000x6000
- be compatible with Inkscape
- each layer should have speaking inkscape labels and SVG ids
- font family for labels should be "Lithos Pro Regular"

The following layers should be present

# Background

As bottom-most layer, the background is just a rectangle over the whole image size with a dark background color (#262626).

# Labels

Above the background layer, a layer with labels for galactic locations should be present.
The labels should be taken from an external JSON file that contains:

- the Inkscape label (from which the SVG id should be derived)
- the x and y coordinates of the label
- (optionally) a rotation value used for a "rotate" transform

Font size should be 56px, color should be "#4d4d4d".

# Grid

Above the label layer, the grid should be placed in a layer.
The grid consists of three parts:

## Center

The center of the image should be marked by a circle with a radius of 150

## Rings

The rings are concentric centered around the center of the image.

- there should be 15 rings
- each ring has a width of 150
- the first ring starts immediately outside the central circle
- the rings should be labeled by numbers, starting with "1" from the innermost ring (the one directly outside the
  central circle)
- the label should be placed along an imaginary line going from the center of the image to the top, centered vertically
  on the ring, to the right of the line.

## Radial Beams

Orientated to the center of the image, there should be radial beams going outwards.

- beams are positioned at an angle of 15 degrees
- they should start at the edge of the central circle
- they should end 150 units outside the outermost ring
- the beams should be labeled by letters, starting with A (until X) going in a counter-clockwise direction from the top
- the label should be placed in the middle between two beams at a position just inside the outer edge of the central
  circle (that is, 15 degrees apart, starting at 7.5 degrees counter-clockwise from the beam going from the center to
  the top of the image)

## Grid Summary

The grid should split the image into 24 * 15 = 360 sectors, plus the central circle.

# Sectors

The topmost layer should contain one layer for each sector as defined by the grid, so a total of 24 * 15 + 1 = 361
layers. Their Inkscape label should correspond to the letter+number combination as defined by the grid, SVG id should be
of the format "sector_<letter><number>".
Each sector should have a hover effect that highlights the sector and shows the sector label.

## Sector Names

Additionally, sectors may be assigned names that should be taken from an external JSON file, which uses a map that
connects the sector label (e.g. "X7" with a name "Proxima Sector"). If a name is present, it should always be visible,
not on hover.

## Star Systems

The script should be able to take a list of star systems in JSON format and place them in the sectors.
The JSON should contain

- the name of the star
- the x and y coordinates of the star
- which coordinate system is being used (galactic or graphic)

For each star, a layer within the sector layer it corresponds to should be created.
This layer should contain:

- a circle with a radius of 1 and a fill color of #ffffff
- a label with the name of the star, which should be visible on hover, font size 5

# Additional notes

All external information that is expected from a JSON file should come from a single JSON file with different fields for
the different types of information (i.e. additional labels for the galaxy, sector names, star systems).

As a supporting resource there is a script in this folder called `sector_assignment.py` that should help associate x+y
coordinates with sectors (it is noteworthy that this file assumes the center to be at 2800 2800, based on an image of
size 5600x5600). It might be good to include the logic there into the script that generates the SVG.

Additionally, there is another script file called `conversion.js` that intends to convert between fictional coordinates
and coordinates within the SVG (it is noteworthy that this file assumes the center to be at 2800 2800, based on an image
of size 5600x5600). It might be good to include the logic there into the script that generates the SVG, and allow the
JSON information for the star systems to specify which coordinate system they are using.