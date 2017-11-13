# PlanetNomadsSavegameEditor
PNSE is a save game editor for the game Planet Nomads by Craneballs.

Disclaimer:
- I am not a developer of Planet Nomads.
- Planet Nomads is developed by Craneballs, their copyright and stuff. See https://www.planet-nomads.com/
- Use the backup button, Planet Nomads is an early access game and may change so bad things can happen when PNSE is not adjusted to changes.

Requirements:
- Python 3.5 or later
- optional: numpy and matplotlib

Usage:
- run GUI.py
- either exit Planet Nomads or at least go to the main menu
- select a saved game
- make a backup
- click one of the buttons
- load the game in Planet Nomads

Advanced Usage:
- Map: drag to rotate. Can be used to locate player and vehicles on the planet. Most of the construct will be crash sites.
- GPS beacons: creates 3 beacons, one at the north pole and two on the equator. They form an equilateral triangle that could be used to check your position on the planet.
- Machine Tools: In Planet Nomads, use the "Rename Block" feature to give a useful name to your machines. This name will show in the machine select instead of the numeric ID.
    - Teleporting: You can teleport your machine around. Please note that machines are not rotated, if you teleport something from the north pole to the south pole it will be upside down.
- Cheats: you're only cheating yourself if you use this too often. 
- Dev Tools: stuff to help me with PNSE.
