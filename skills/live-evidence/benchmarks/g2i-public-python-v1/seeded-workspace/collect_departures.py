"""Owned clean-room candidate implementation of the pinned public task.

Contains ONE genuine runtime-state defect relevant to the task: the date
filter compares ISO zero-padded dates ("2018-07-15") against the unpadded
literal "2018-6-1", and because "0" < "6" in a string comparison EVERY real
date fails the filter, so the CSV is silently empty. The defect is invisible
in the code path (no exception, exit 0) and observable in paused runtime
state: the comparison operands at the filter line.
"""

import csv
import json
from pathlib import Path

PAGE_SIZE = 3


def fetch_page(pages, offset):
    """Stand-in for the local API client: returns one paginated response."""
    results = pages[offset:offset + PAGE_SIZE]
    next_offset = offset + PAGE_SIZE
    return {
        "count": len(pages),
        "next": f"/departures/?limit={PAGE_SIZE}&offset={next_offset}" if next_offset < len(pages) else None,
        "results": results,
    }


def collect_all(pages):
    departures = []
    offset = 0
    while True:
        page = fetch_page(pages, offset)
        departures.extend(page["results"])
        if page["next"] is None:
            return departures
        offset += PAGE_SIZE


def main():
    data = json.loads((Path(__file__).parent / "departures.json").read_text())
    departures = collect_all(data)
    cutoff = "2018-6-1"  # DEFECT: unpadded; every zero-padded ISO date sorts below it
    kept = [
        d for d in departures
        if d["start_date"] > cutoff and d["category"] == "Adventurous"
    ]
    out = Path(__file__).parent / "filtered_departures.csv"
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        if kept:
            headers = [key.replace("_", " ").title() for key in kept[0]]
            writer.writerow(headers)
            for d in kept:
                writer.writerow(list(d.values()))
    print(len(kept))


if __name__ == "__main__":
    main()
