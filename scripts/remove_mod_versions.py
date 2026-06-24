#!/usr/bin/env python3
"""Remove version fields from Reforger config mod entries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize Reforger config game.mods entries so each mod only has "
            "modId and name."
        )
    )
    parser.add_argument(
        "configs",
        nargs="+",
        type=Path,
        help="Path(s) to Reforger server config JSON files to update.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing files.",
    )
    return parser.parse_args()


def load_config(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        raise ValueError(f"{path}: file does not exist") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: invalid JSON at line {error.lineno}: {error.msg}") from None


def normalize_mods(config: Any, path: Path) -> int:
    try:
        mods = config["game"]["mods"]
    except (KeyError, TypeError):
        raise ValueError(f"{path}: expected game.mods array") from None

    if not isinstance(mods, list):
        raise ValueError(f"{path}: expected game.mods to be an array")

    changed = 0
    for index, mod in enumerate(mods):
        if not isinstance(mod, dict):
            raise ValueError(f"{path}: expected game.mods[{index}] to be an object")

        missing = [key for key in ("modId", "name") if key not in mod]
        if missing:
            missing_keys = ", ".join(missing)
            raise ValueError(f"{path}: game.mods[{index}] is missing {missing_keys}")

        normalized = {"modId": mod["modId"], "name": mod["name"]}
        if mod != normalized:
            mods[index] = normalized
            changed += 1

    return changed


def write_config(path: Path, config: Any) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)
        file.write("\n")


def main() -> int:
    args = parse_args()
    failed = False

    for path in args.configs:
        try:
            config = load_config(path)
            changed = normalize_mods(config, path)
        except ValueError as error:
            print(error, file=sys.stderr)
            failed = True
            continue

        if changed == 0:
            print(f"{path}: no mod entries needed changes")
            continue

        if args.dry_run:
            print(f"{path}: would update {changed} mod entries")
        else:
            write_config(path, config)
            print(f"{path}: updated {changed} mod entries")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
