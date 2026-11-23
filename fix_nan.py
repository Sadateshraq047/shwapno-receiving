"""One-time repair: turns NaN into null in data/meta.json and data/open_*.json.gz (no MySQL needed)."""
import os, json, gzip, math, glob
here = os.path.dirname(os.path.abspath(__file__))
d = os.path.join(here, "data")

def clean(o):
    if isinstance(o, dict):  return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):  return [clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o): return None
    return o

p = os.path.join(d, "meta.json")
with open(p, encoding="utf-8") as f: m = json.load(f)
with open(p, "w", encoding="utf-8") as f: json.dump(clean(m), f, separators=(",", ":"), allow_nan=False)
print("fixed meta.json")
for fp in sorted(glob.glob(os.path.join(d, "open_*.json.gz"))):
    with gzip.open(fp, "rt", encoding="utf-8") as f: js = json.load(f)
    with gzip.open(fp, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(clean(js), f, separators=(",", ":"), allow_nan=False)
    print("fixed", os.path.basename(fp))
print("Done. Refresh the browser (Ctrl+F5).")
