"""Creates DEMO data (fake numbers) in ./data so you can preview the dashboard before running the real builder.
Run:  python make_demo_data.py"""
import json, os, gzip, random, datetime as dt
import numpy as np
random.seed(7); rng = np.random.default_rng(7)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)
for _f in os.listdir(OUT):
    os.remove(os.path.join(OUT, _f))

DIST = {"Dhaka": ["Dhaka","Gazipur","Narayanganj","Savar","Tangail","Manikganj"], "Chattogram": ["Chittagong","Cumilla","Feni","Noakhali","Cox's Bazar"],
        "Khulna": ["Khulna","Jashore","Satkhira","Kushtia"], "Rajshahi": ["Rajshahi","Bogura","Pabna","Natore"], "Rangpur": ["Rangpur","Dinajpur","Gaibandha"],
        "Barishal": ["Barishal","Bhola","Patuakhali"], "Mymensingh": ["Mymensingh","Jamalpur"], "Sylhet": ["Sylhet","Moulvibazar"]}
WEIGHT = {"Dhaka": 8, "Chattogram": 4, "Khulna": 2, "Rajshahi": 2, "Rangpur": 1.5, "Barishal": 1.2, "Mymensingh": 1, "Sylhet": 1}
outlets = []
n = 0
for reg, ds in DIST.items():
    for d in ds:
        for k in range(max(1, int(WEIGHT[reg] * rng.integers(2, 6)))):
            n += 1
            outlets.append([f"{reg[0]}{n:03d}", f"{reg[0]}{n:03d}-{d} {k+1}", reg, d, f"{d} Zone" if reg != "Dhaka" else random.choice(["Savar Zone","Gazipur Zone","Old Town Zone","Uttara Zone"])])
MAST = {"FRESH PRODUCE": ["FRUITS","VEGETABLES","MEAT","FISH"], "PACKED COMMODITY": ["RICE","OIL","FLOUR","SUGAR","LENTILS"],
        "COMPANY GOODS": ["BISCUITS","NOODLES","BEVERAGES","SNACKS","DAIRY"], "GENERAL MERCHANDISE": ["HOME CARE","KITCHENWARE","STATIONERY"],
        "LIFESTYLE": ["BABY CARE","PERSONAL CARE","APPAREL"]}
combos = [[m, c] for m, cs in MAST.items() for c in cs]
articles = []
for i in range(1800):
    m, c = combos[rng.integers(len(combos))]
    articles.append([str(2100000 + i * 37), f"{c.title()} item {i}", c, m, float(rng.choice([7, 10, 15, 21, 30, 45, 60, 120]))])
combo_of = {(a[3], a[2]): combos.index([a[3], a[2]]) for a in articles}

closing = dt.date(2026, 11, 22)
openings = [dt.date(2026, 9, 27) + dt.timedelta(days=7 * i) for i in range(8)]
files = []
def cols(rows, keys): return {k: [r[k] for r in rows] for k in keys}
for oi, op in enumerate(openings):
    frac = 1 - oi * 0.1
    over, under, cells = [], [], {}
    for o, out in enumerate(outlets):
        bias = rng.uniform(0.4, 1.6)
        cats = rng.choice(len(combos), size=rng.integers(6, 14), replace=False)
        for c in cats:
            base = int(rng.integers(8, 60) * frac) + 1
            nover = int(base * rng.uniform(0.05, 0.35) * bias); nunder = int(base * rng.uniform(0.03, 0.2))
            cells[(o, int(c))] = [base, nover, nunder, 0, 0, 0, 0, 0]
            pool = [i for i, a in enumerate(articles) if combo_of[(a[3], a[2])] == c]
            for _ in range(nover):
                a = int(rng.choice(pool)); recv = float(rng.integers(12, 900)); sales = float(rng.integers(0, 300)); op_st = float(rng.integers(0, 200))
                est = float(sales * rng.uniform(0.2, 1.5)); inv = recv + op_st
                q = max(1.0, min(recv, inv - sales - est)) if inv - sales - est > 0 else float(rng.integers(5, 80))
                q = min(q, recv); score = min(3.0, q * 3 / recv); val = q * float(rng.uniform(20, 400))
                over.append(dict(o=o, a=a, qty=round(q, 1), score=round(score, 3), recv=recv, sales=sales, inv=inv, open=op_st, est=round(est, 1), value=round(val),
                                 po=str(4500000000 + int(rng.integers(1, 99999))) + (", " + str(4500000000 + int(rng.integers(1, 99999))) if rng.random() < .25 else ""), mov=random.choice(["101","101, 102","351","101, 653"])))
                cells[(o, int(c))][3] += q; cells[(o, int(c))][4] += val; cells[(o, int(c))][6] += recv; cells[(o, int(c))][7] += sales
            for _ in range(nunder):
                a = int(rng.choice(pool)); sales = float(rng.integers(12, 500)); req = sales * rng.uniform(1.2, 3); inv = float(rng.integers(5, int(req)))
                q = req - inv; score = min(3.0, q * 3 / req)
                under.append(dict(o=o, a=a, qty=round(q, 1), score=round(score, 3), recv=float(rng.integers(0, 200)), sales=sales, inv=inv, open=float(rng.integers(0, 60)), req=round(req, 1)))
                cells[(o, int(c))][5] += q; cells[(o, int(c))][7] += sales
    over.sort(key=lambda r: -r["score"]); under.sort(key=lambda r: -r["score"])
    keys = list(cells)
    js = dict(opening=str(op), closing=str(closing),
              kpi=dict(pairs=sum(v[0] for v in cells.values()), over_incidents=len(over), under_incidents=len(under)),
              over=cols(over, ["o","a","qty","score","recv","sales","inv","open","est","value","po","mov"]),
              under=cols(under, ["o","a","qty","score","recv","sales","inv","open","req"]),
              cells=dict(o=[k[0] for k in keys], c=[k[1] for k in keys], base=[cells[k][0] for k in keys], oi=[cells[k][1] for k in keys], ui=[cells[k][2] for k in keys],
                         oq=[round(cells[k][3]) for k in keys], ov=[round(cells[k][4]) for k in keys], uq=[round(cells[k][5]) for k in keys],
                         rq=[round(cells[k][6]) for k in keys], sq=[round(cells[k][7]) for k in keys]))
    fn = f"open_{op}.json.gz"; f_ = gzip.open(os.path.join(OUT, fn), "wt", encoding="utf-8"); json.dump(js, f_, separators=(",", ":")); f_.close(); files.append(fn)
meta = dict(generated="DEMO DATA", closing=str(closing), openings=[str(o) for o in openings], files=files, combos=combos, outlets=outlets, articles=articles, demo=True)
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), separators=(",", ":"))
print("demo data written to", OUT)
