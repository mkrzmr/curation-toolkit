"""
Run once after installing dependencies:
    python3 setup.py

Creates the data/ directory where snapshots are stored.
Snapshots are downloaded automatically via the "Get latest data from GitHub"
button in the sidebar, or you can place full_items_*.json files here manually.
"""
import pathlib

DATA = pathlib.Path(__file__).parent / "data"

if DATA.exists():
    print("data/ already exists — nothing to do.")
else:
    DATA.mkdir()
    print("Created data/")

print("Setup complete.")
