"""
Shwapno - Over / Under Receiving data builder
=============================================
Reads fact tables from MySQL (pc2) and dimension sheets from Excel, recomputes the
Power BI "Over/Under Receiving" logic for every Sunday opening date inside a rolling
2-month window, and writes compact JSON files for the HTML dashboard.

Rules (from the Power BI model + your instructions)
  * CLOSING date is fixed = latest date available in the data (nobody can change it).
  * OPENING date = any Sunday in the window (opening stock is preserved on Sundays).
  * WINDOW = starts on the first Sunday on/after (closing - 2 months).

Run:   python build_receiving_data.py            (asks for the MySQL password)
Needs: pip install pandas numpy sqlalchemy pymysql openpyxl
"""
import os
import time, sys, json, gzip, getpass, datetime as dt
import numpy as np
import pandas as pd

CFG = dict(
    host="127.0.0.1", port=3306, user="root", db="pc2",
    dim_xlsx=r"D:\pc2\SDT_Database_Template (2).xlsx",
    out_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),   # always the data folder next to this script
    window_months=2,
    closing_override=None,       # e.g. "2026-11-22" to force a closing date
    max_rows_per_table=150000,   # keep the top-N incidents per opening (by score)
)

# ----------------------------------------------------------------------------- helpers
def clean_code(s):
    """'2100001.0' -> '2100001', trims spaces (same idea as the Power BI 'New Artilce Column')."""
    s = s.astype("string").str.strip()
    return s.str.replace(r"\.0$", "", regex=True)

def first_sunday_on_or_after(d):
    d = pd.Timestamp(d).normalize()
    return d + pd.Timedelta(days=(6 - d.weekday()) % 7)   # Monday=0 ... Sunday=6

def r2(a, n=2):
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), n) for v in a]

# ----------------------------------------------------------------------------- core logic
def prepare_sales_global(sales_w):
    """Average daily sales per outlet+article over the WHOLE window
    (Power BI: first sale day -> last sale day, ignoring the date slicer)."""
    g = sales_w.groupby(["outlet", "article"]).agg(q_all=("q", "sum"), mn=("mn", "min"), mx=("mx", "max"))
    g["days"] = (g["mx"] - g["mn"]).dt.days + 1
    g["avg_sales"] = g["q_all"] / g["days"]
    return g[["avg_sales"]]

def compute_opening(O, C, sales_w, avg_g, stock, recv, art, cutoff):
    """One opening scenario. Returns (pairs DataFrame with all measures)."""
    O, C = pd.Timestamp(O), pd.Timestamp(C)
    r = recv[(recv.posting_date >= O) & (recv.posting_date <= C)]
    base = r.groupby(["outlet", "article"]).agg(recv_q=("q", "sum"), recv_amt=("amt", "sum"))
    first_pos = r[r.q > 0].groupby(["outlet", "article"]).posting_date.min().rename("first_pos")
    base = base.join(first_pos)

    s = sales_w[sales_w.wk >= O].groupby(["outlet", "article"]).agg(sales_q=("q", "sum"), cogs=("cogs", "sum"))
    st = stock[stock.date == O].groupby(["outlet", "article"]).qty.sum().rename("open_stock")
    d = base.join(s).join(st).join(avg_g)
    d = d.join(art[["std_days"]], on="article")
    for c in ("sales_q", "cogs", "open_stock", "avg_sales"):
        d[c] = d[c].fillna(0.0)

    d["inv"] = d.recv_q + d.open_stock                                   # Total Inventory
    std = d.std_days
    d["est_close"] = np.where(std.isna(), 0.0, d.avg_sales * std)        # Est. Closing Stock
    overstock = d.inv - d.sales_q - d.est_close

    # ---- Over receiving
    d["over"] = np.where(overstock > 0, np.minimum(overstock, d.recv_q), np.nan)
    ok = ((d.over > 0) & (d.recv_q > 10) & (d.inv > 0) & ((d.inv - d.over) > 0)
          & (d.first_pos.isna() | (d.first_pos <= cutoff)))
    d["over_score"] = np.where(ok, d.over * 3 / d.recv_q.replace(0, np.nan), np.nan)

    q1 = np.maximum(0, np.where(d.sales_q != 0, d.cogs / d.sales_q.replace(0, np.nan), 0))
    q3 = np.maximum(0, np.where(d.recv_q != 0, d.recv_amt / d.recv_q.replace(0, np.nan), 0))
    cpu = np.where(q1 == 0, q3, q1)
    d["over_value"] = np.where(d.over.notna(), np.maximum(0, d.over * cpu), np.nan)

    # ---- Under receiving (standard days capped at 100 days of average sales)
    est_u = np.where(std > 100, d.avg_sales * 100, d.est_close)
    ov_u = d.inv - d.sales_q - est_u
    d["under"] = np.where(ov_u < 0, ov_u, np.nan)
    required = d.sales_q + est_u
    uok = (d.under.abs() > 0) & (d.sales_q > 10) & (required > 0) & (d.inv >= 5)
    d["under_score"] = np.where(uok, np.minimum(3, d.under.abs() * 3 / np.where(required > 0, required, np.nan)), np.nan)
    d["required"] = required
    return d.reset_index()

# ----------------------------------------------------------------------------- output
def build_opening_json(O, C, d, recv, art_idx, out_idx, art, outlets, cfg):
    O, C = pd.Timestamp(O), pd.Timestamp(C)
    combos = sorted(set(zip(art.master.fillna("Unknown"), art.cat3.fillna("Unknown"))))
    combo_idx = {c: i for i, c in enumerate(combos)}
    d = d.copy()
    d["cat3"] = [combo_idx[(m, c)] for m, c in zip(d.article.map(art.master).fillna("Unknown"),
                                                   d.article.map(art.cat3).fillna("Unknown"))]
    d["o"] = d.outlet.map(out_idx)
    d["a"] = d.article.map(art_idx)

    # outlet x (master, category3) cells (denominator for incident %)
    d["oi"] = d.over_score.notna().astype(int)
    d["ui"] = d.under_score.notna().astype(int)
    d["oq"] = np.where(d.oi == 1, d.over, 0.0)
    d["ov"] = np.where(d.oi == 1, d.over_value, 0.0)
    d["uq"] = np.where(d.ui == 1, d.under.abs(), 0.0)
    d["one"] = 1
    cells = d.groupby(["o", "cat3"]).agg(base=("one", "sum"), oi=("oi", "sum"), ui=("ui", "sum"),
                                         oq=("oq", "sum"), ov=("ov", "sum"), uq=("uq", "sum"),
                                         rq=("recv_q", "sum"), sq=("sales_q", "sum")).reset_index()

    ov = d[d.over_score.notna()].sort_values(["over_score", "over"], ascending=False).head(cfg["max_rows_per_table"])
    un = d[d.under_score.notna()].sort_values(["under_score"], ascending=False).head(cfg["max_rows_per_table"])

    # PO numbers and movement types for the over-receiving incidents
    r = recv[(recv.posting_date >= O) & (recv.posting_date <= C)]
    key = ov[["outlet", "article"]]
    rr = r.merge(key, on=["outlet", "article"])
    agg = rr.groupby(["outlet", "article"]).agg(
        po=("po", lambda x: ", ".join(sorted(set(x.dropna().astype(str))))[:200]),
        mov=("mov", lambda x: ", ".join(sorted(set(x.dropna().astype(str))))[:60])).reset_index()
    ov = ov.merge(agg, on=["outlet", "article"], how="left")

    def over_cols(t):
        return dict(o=t.o.tolist(), a=t.a.tolist(), qty=r2(t.over), score=r2(t.over_score, 3),
                    recv=r2(t.recv_q), sales=r2(t.sales_q), inv=r2(t.inv), open=r2(t.open_stock),
                    est=r2(t.est_close), value=r2(t.over_value, 0),
                    po=t.po.fillna("").tolist(), mov=t.mov.fillna("").tolist())

    def under_cols(t):
        return dict(o=t.o.tolist(), a=t.a.tolist(), qty=r2(t.under.abs()), score=r2(t.under_score, 3),
                    recv=r2(t.recv_q), sales=r2(t.sales_q), inv=r2(t.inv), open=r2(t.open_stock),
                    req=r2(t.required))

    kpi = dict(pairs=int(len(d)),
               over_incidents=int(d.over_score.notna().sum()), under_incidents=int(d.under_score.notna().sum()),
               over_qty=float(d.loc[d.over_score.notna(), "over"].sum()),
               over_value=float(d.loc[d.over_score.notna(), "over_value"].sum()),
               under_qty=float(d.loc[d.under_score.notna(), "under"].abs().sum()),
               receiving_qty=float(d.recv_q.sum()), sales_qty=float(d.sales_q.sum()))
    return dict(opening=O.strftime("%Y-%m-%d"), closing=C.strftime("%Y-%m-%d"),
                kpi=kpi, over=over_cols(ov), under=under_cols(un),
                cells=dict(o=cells.o.tolist(), c=cells.cat3.tolist(), base=cells.base.tolist(),
                           oi=cells.oi.tolist(), ui=cells.ui.tolist(),
                           oq=cells.oq.round(0).tolist(), ov=cells.ov.round(0).tolist(), uq=cells.uq.round(0).tolist(),
                           rq=cells.rq.round(0).tolist(), sq=cells.sq.round(0).tolist())), [list(c) for c in combos]


def clean_nan(o):
    """Replace NaN/NaT/pd.NA/inf with None so the JSON is valid for browsers."""
    if isinstance(o, dict):
        return {k: clean_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_nan(v) for v in o]
    try:
        if o is None or o is pd.NA or o is pd.NaT:
            return None
        if isinstance(o, (float, np.floating)) and not np.isfinite(o):
            return None
    except Exception:
        pass
    return o

# ----------------------------------------------------------------------------- data loading
def load_dims(cfg):
    print("Reading dimension sheets (the big Excel file takes a minute)...")
    a = pd.read_excel(cfg["dim_xlsx"], sheet_name="DimArticle", dtype=str)
    o = pd.read_excel(cfg["dim_xlsx"], sheet_name="DimOutlet", dtype=str)
    art = pd.DataFrame({
        "article": clean_code(a["ArticleNo"]), "name": a["ArticleName"], "cat3": a["Category3"],
        "master": a["MasterCategory"],
        "std_days": pd.to_numeric(a["No. Of Std Stock Days"], errors="coerce")}).dropna(subset=["article"])
    art = art.drop_duplicates("article").set_index("article")
    outlets = pd.DataFrame({
        "outlet": o["OutletCode"].str.strip(), "name": o["OutletName"], "region": o["RegionName"],
        "district": o["Google Map Location"], "zone": o["Zone"]}).dropna(subset=["outlet"])
    outlets = outlets.drop_duplicates("outlet").set_index("outlet")
    return art, outlets

def load_facts(cfg, pwd):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    eng = create_engine(URL.create("mysql+pymysql", username=cfg["user"], password=pwd,
                                   host=cfg["host"], port=cfg["port"], database=cfg["db"]))
    q = lambda sql, **p: pd.read_sql(sql, eng, params=p)

    if cfg["closing_override"]:
        C = pd.Timestamp(cfg["closing_override"])
    else:
        print("Finding the closing date...")
        s_max = q("SELECT MAX(Stock_Date) d FROM stocktable").d[0]
        b_max = q("SELECT MAX(BillingDate) d FROM DimFactDailySales").d[0]
        C = pd.Timestamp(min(s_max, b_max))
    start = first_sunday_on_or_after(C - pd.DateOffset(months=cfg["window_months"]))
    openings = list(pd.date_range(start, C - pd.Timedelta(days=1), freq="7D"))
    print(f"Closing {C.date()} | window starts {start.date()} | {len(openings)} Sunday openings")
    s, c = start.strftime("%Y-%m-%d"), C.strftime("%Y-%m-%d")

    print("Loading sales (streaming rows; no MySQL grouping, no table changes)...")
    parts, nrows = [], 0
    sql = """SELECT Payer AS outlet, Material AS article, BillingDate AS d,
                    ActualInvoicedQuantity AS q, COGS AS cogs
             FROM DimFactDailySales WHERE BillingDate BETWEEN %(s)s AND %(c)s"""
    with eng.connect().execution_options(stream_results=True) as conn:
        for ch in pd.read_sql(sql, conn, params={"s": s, "c": c}, chunksize=200000):
            ch["outlet"] = ch.outlet.astype("string").str.strip()
            ch["article"] = clean_code(ch.article)
            ch["d"] = pd.to_datetime(ch.d)
            ch["wk"] = ch.d - pd.to_timedelta((ch.d.dt.dayofweek + 1) % 7, unit="D")   # Sunday of that week
            ch["q"] = pd.to_numeric(ch.q, errors="coerce").fillna(0)
            ch["cogs"] = pd.to_numeric(ch.cogs, errors="coerce").fillna(0)
            g = ch.groupby(["outlet", "article", "wk"], as_index=False).agg(
                q=("q", "sum"), cogs=("cogs", "sum"), mn=("d", "min"), mx=("d", "max"))
            parts.append(g)
            nrows += len(ch)
            print(f"   ...{nrows:,} sales rows read", flush=True)
    sales_w = pd.concat(parts, ignore_index=True).groupby(["outlet", "article", "wk"], as_index=False).agg(
        q=("q", "sum"), cogs=("cogs", "sum"), mn=("mn", "min"), mx=("mx", "max"))

    print("Loading stock on opening/closing days (streaming)...", flush=True)
    days = ",".join(f"'{d.strftime('%Y-%m-%d')}'" for d in openings + [C])
    t0 = time.time(); parts, n = [], 0
    sql = f"""SELECT OutletCode AS outlet, ProductCode AS article, Stock_QTY AS qty, Stock_Date AS date
              FROM stocktable WHERE Stock_Date IN ({days})"""
    with eng.connect().execution_options(stream_results=True) as conn:
        for ch in pd.read_sql(sql, conn, chunksize=200000):
            ch["outlet"] = ch.outlet.astype("string").str.strip()
            ch["article"] = clean_code(ch.article)
            ch["date"] = pd.to_datetime(ch["date"])
            ch["qty"] = pd.to_numeric(ch.qty, errors="coerce").fillna(0)
            parts.append(ch.groupby(["outlet", "article", "date"], as_index=False).qty.sum())
            n += len(ch)
            print(f"   ...{n:,} stock rows read ({time.time()-t0:,.0f}s)", flush=True)
    stock = pd.concat(parts, ignore_index=True).groupby(["outlet", "article", "date"], as_index=False).qty.sum()

    print("Loading receiving (streaming)...", flush=True)
    t0 = time.time(); parts, n = [], 0
    sql = """SELECT plant AS outlet, material AS article, posting_date, purchase_order AS po,
                    movement_type AS mov, qty_in_unit_of_entry AS q, amt_in_loc_cur AS amt
             FROM receiving
             WHERE document_date BETWEEN %(s)s AND %(c)s
               AND NOT (COALESCE(movement_type,'')='303' AND COALESCE(qty_in_unit_of_entry,0)>0)"""
    with eng.connect().execution_options(stream_results=True) as conn:
        for ch in pd.read_sql(sql, conn, params={"s": s, "c": c}, chunksize=200000):
            parts.append(ch); n += len(ch)
            print(f"   ...{n:,} receiving rows read ({time.time()-t0:,.0f}s)", flush=True)
    recv = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["outlet", "article", "posting_date", "po", "mov", "q", "amt"])
    recv["posting_date"] = pd.to_datetime(recv.posting_date)
    recv["outlet"] = recv.outlet.astype("string").str.strip()
    recv["article"] = clean_code(recv.article)
    recv["po"] = clean_code(recv.po)
    return C, openings, sales_w, stock, recv

# ----------------------------------------------------------------------------- main
def run(cfg, pwd):
    art, outlets = load_dims(cfg)
    C, openings, sales_w, stock, recv = load_facts(cfg, pwd)

    # keep only rows that exist in the dimensions (Power BI drops the others into a blank member)
    sales_w = sales_w[sales_w.outlet.isin(outlets.index) & sales_w.article.isin(art.index)]
    recv = recv[recv.outlet.isin(outlets.index) & recv.article.isin(art.index)]
    stock = stock[stock.outlet.isin(outlets.index) & stock.article.isin(art.index)]

    avg_g = prepare_sales_global(sales_w)
    cutoff = recv.posting_date.max() - pd.Timedelta(days=7)

    art_idx = {a: i for i, a in enumerate(art.index)}
    out_idx = {o: i for i, o in enumerate(outlets.index)}
    os.makedirs(cfg["out_dir"], exist_ok=True)
    for old in os.listdir(cfg["out_dir"]):                      # remove files from earlier runs / demo data
        if old.startswith("open_") or old == "meta.json":
            os.remove(os.path.join(cfg["out_dir"], old))
    cat3_list = None
    results = []
    for O in openings:
        d = compute_opening(O, C, sales_w, avg_g, stock, recv, art, cutoff)
        js, cat3_list = build_opening_json(O, C, d, recv, art_idx, out_idx, art, outlets, cfg)
        results.append(js)
        print(f"  {O.date()}: {js['kpi']['pairs']:,} pairs | over {js['kpi']['over_incidents']:,} | "
              f"under {js['kpi']['under_incidents']:,}")

    # keep only the articles that appear in an incident table -> small meta.json
    used = sorted({a for js in results for k in ("over", "under") for a in js[k]["a"]})
    remap = {old: new for new, old in enumerate(used)}
    art_list = list(art.index)
    files = []
    for js in results:
        for k in ("over", "under"):
            js[k]["a"] = [remap[a] for a in js[k]["a"]]
        fn = "open_%s.json.gz" % js["opening"]
        fp = os.path.join(cfg["out_dir"], fn)
        with gzip.open(fp, "wt", encoding="utf-8", compresslevel=9) as f:
            json.dump(clean_nan(js), f, separators=(",", ":"), allow_nan=False)
        print(f"  wrote {fn}  {os.path.getsize(fp)//1024:,} KB")
        files.append(fn)

    meta = dict(generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"), closing=C.strftime("%Y-%m-%d"),
                openings=[O.strftime("%Y-%m-%d") for O in openings], files=files, combos=cat3_list,
                outlets=[[c, r["name"], r["region"], r["district"], r["zone"]] for c, r in outlets.iterrows()],
                articles=[[art_list[i], art.iloc[i]["name"], art.iloc[i]["cat3"], art.iloc[i]["master"],
                           None if pd.isna(art.iloc[i]["std_days"]) else float(art.iloc[i]["std_days"])] for i in used])
    with open(os.path.join(cfg["out_dir"], "meta.json"), "w") as f:
        json.dump(clean_nan(meta), f, separators=(",", ":"), allow_nan=False)
    print("Done ->", cfg["out_dir"])

if __name__ == "__main__":
    pwd = os.environ.get("MYSQL_PWD") or getpass.getpass("MySQL password for %s@%s: " % (CFG["user"], CFG["host"]))
    run(CFG, pwd)
