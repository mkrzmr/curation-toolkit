"""
Run once before starting the app:
    python setup.py

Creates symlinks so the app reads sshompitor's data and config without copying.
"""
import os
import pathlib

BASE = pathlib.Path(__file__).parent
SSHOMPITOR = BASE.parent / "sshompitor"

links = {
    BASE / "data": SSHOMPITOR / "data",
    BASE / "config.yaml": SSHOMPITOR / "config.yaml",
}

for link, target in links.items():
    if not target.exists():
        print(f"WARNING: target does not exist: {target}")
        continue
    if link.exists() or link.is_symlink():
        print(f"Already exists, skipping: {link.name}")
    else:
        link.symlink_to(target)
        print(f"Created symlink: {link.name} -> {target}")

print("Setup complete.")
