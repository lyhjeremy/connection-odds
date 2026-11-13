"""python -m agent < itinerary.txt   prints the answer; add --trace for the full record as JSON."""
import json
import sys

from .pipeline import check_itinerary

if __name__ == "__main__":
    out = check_itinerary(sys.stdin.read())
    print(out["answer"])
    if "--trace" in sys.argv:
        print(json.dumps(out, indent=1, default=str))
