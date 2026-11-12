# BOXLAB

# by @mdrndesigns

Parametric storage tray + lid. Sliders in the browser, CadQuery on the server. By @mdrndesigns.

## Run

    cd ~/cad/boxlab
    python3 app.py

Opens http://localhost:8765. Ctrl-C to stop.
Port clash: `python3 app.py --port 8766`

## Files

    model.py     geometry only - the part is defined here
    app.py       local server, no framework, stdlib only
    index.html   slider UI + three.js viewport

## Export

The Export button downloads a zip:

    <name>_tray.step / .stl / .3mf
    <name>_lid.step / .stl / .3mf
    <name>_parameters.json     the exact slider state
    <name>_model.py            standalone script that rebuilds it

Print the tray as-is (open face up, no support). The lid exports plate-down,
lip up - also support-free.

## Defaults

0.4 mm nozzle, 0.2 mm layer, PLA.
Wall 2.4 mm = 6 perimeters. Floor 1.2 mm = 6 layers.
Lid clearance 0.25 mm per face - the mating-parts value for FDM.

## Changing the part

Geometry lives in model.py. Adding a parameter takes two edits:
add it to DEFAULTS, then add a row to CONTROLS in index.html.
