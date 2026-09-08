"""Export locked PyPI dependencies; fail if Pixi's JSON schema stops matching."""

import json
import sys


def requirements(packages):
    selected = sorted(
        f"{package['name']}=={package['version']}"
        for package in packages
        if package.get("kind") == "pypi"
        and package["name"].replace("_", "-").lower() != "geode-gnss"
    )
    if not selected:
        raise ValueError(
            "No PyPI dependencies found; refusing to report an empty audit."
        )
    return "\n".join(selected) + "\n"


if __name__ == "__main__":
    sys.stdout.write(requirements(json.load(sys.stdin)))
