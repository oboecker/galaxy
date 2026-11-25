#!/usr/bin/env node

// To be used with "001-galaxy.original.svg" (now assets/galaxy/history/)

const center = {
    galactic: {x: 0, y: 0, z: 0},
    graphic: {x: 2800, y: 2800}
}
const sol = {
    galactic: {x: -513, y: 24995, z: 50},
    graphic: {x: 2778, y: 1745}
}

// z-coordinate is not relevant for conversion
async function galacticToGraphic(x, y, z = 0) {
    const dx = sol.graphic.x - center.graphic.x;
    const dy = sol.graphic.y - center.graphic.y;

    const fx = dx / sol.galactic.x;
    const fy = dy / sol.galactic.y;

    const nx = (x * fx) + center.graphic.x;
    const ny = (y * fy) + center.graphic.y;

    return {x: Math.floor(nx), y: Math.floor(ny)};
}

async function graphicToGalactic(x, y, z = 0) {
    const dx = sol.graphic.x - center.graphic.x;
    const dy = sol.graphic.y - center.graphic.y;

    const fx = dx / sol.galactic.x;
    const fy = dy / sol.galactic.y;

    const sx = (x - center.graphic.x) / fx;
    const sy = (y - center.graphic.y) / fy;

    return {x: Math.floor(sx), y: Math.floor(sy)};
}

galacticToGraphic(process.argv[2], process.argv[3]).then(value => {
    // first number the coordinate, second number where to put the dot in inkscape
    console.log("X: " + value.x + " (" + (value.x - 1) + ")");
    console.log("Y: " + value.y + " (" + (value.y - 1) + ")");
});

// graphicToGalactic(process.argv[2], process.argv[3]).then(value => {
//     console.log("X: " + value.x);
//     console.log("Y: " + value.y);
// });
