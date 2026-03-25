"""sqlens CLI — command line interface (v0.6).

Planned commands:
    sqlens inspect --bigquery project.dataset
    sqlens enrich ./catalog.json --descriptions --stats
    sqlens context ./catalog.json "monthly active users by country"
"""

from __future__ import annotations

import sys


def main() -> None:
    print("sqlens CLI is planned for v0.6")
    print("For now, use the Python API: from sqlens import SQLens")
    sys.exit(0)


if __name__ == "__main__":
    main()
