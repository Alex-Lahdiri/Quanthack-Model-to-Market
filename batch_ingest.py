"""
Resilient, checkpointed ingestion for the big archive (works around per-command
time limits). Each run processes as many files as fit in --max-seconds, writes
their bars to a part file, and records progress. Re-run until "ALL FILES DONE",
then run once with --finalize to assemble + cache the panel.

For --freq 1m we use a fast minute-bucket resampler (string-slice the timestamp
instead of parsing every tick) -- big speedup on the heavy metals files.
"""
from __future__ import annotations

import argparse, glob, os, re, sys, time, zipfile
import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_loader as dl

PAT = re.compile(r"(?:^|/)([A-Za-z0-9]+)_(\d{4})_(\d{2})_(\d{2})\.parquet$")


def fast_bars_1m(path: str) -> pl.DataFrame:
    """1-min OHLC by bucketing the 'YYYY-MM-DD HH:MM:SS...' timestamp string to
    its first 16 chars. Assumes the file is time-ordered (these are). Falls back
    to the generic loader if the timestamp isn't a string."""
    lf = pl.scan_parquet(path)
    m = dl.detect_columns(lf.collect_schema().names())
    ts, sym = m["ts"], m["symbol"]
    if lf.collect_schema()[ts] != pl.Utf8:
        return dl.to_bars(dl.load_quotes(path), "1m")
    have = bool(m.get("bid") and m.get("ask"))
    sel = [pl.col(ts).str.slice(0, 16).alias("minute"),
           pl.col(sym).cast(pl.Utf8).alias("symbol")]
    if have:
        sel += [((pl.col(m["bid"]) + pl.col(m["ask"])) / 2).alias("mid"),
                (pl.col(m["ask"]) - pl.col(m["bid"])).alias("spread")]
    else:
        sel += [pl.col(m["price"]).alias("mid"), pl.lit(0.0).alias("spread")]
    bars = (lf.select(sel)
            .group_by(["symbol", "minute"], maintain_order=True)
            .agg(pl.col("mid").first().alias("open"), pl.col("mid").max().alias("high"),
                 pl.col("mid").min().alias("low"), pl.col("mid").last().alias("close"),
                 pl.col("spread").mean().alias("mean_spread"))
            .collect())
    return (bars.with_columns(pl.col("minute").str.to_datetime("%Y-%m-%d %H:%M", strict=False).alias("ts"))
            .drop("minute").select(["ts", "symbol", "open", "high", "low", "close", "mean_spread"]))


def members(zip_path, instruments, start, end):
    z = zipfile.ZipFile(zip_path)
    out = []
    for n in z.namelist():
        mt = PAT.search(n)
        if not mt:
            continue
        sym, d = mt.group(1), f"{mt.group(2)}-{mt.group(3)}-{mt.group(4)}"
        if instruments and sym not in instruments:
            continue
        if start and d < start:
            continue
        if end and d > end:
            continue
        out.append((n, sym, d))
    out.sort(key=lambda x: (x[1], x[2]))
    return z, out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--instruments", default="")
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")
    ap.add_argument("--freq", default="1m")
    ap.add_argument("--max-seconds", type=float, default=35.0)
    ap.add_argument("--state", default="/tmp/ingest_state")
    ap.add_argument("--workdir", default="/tmp/_ingest")
    ap.add_argument("--cache", default=os.path.join(here, "results", "panel.parquet"))
    ap.add_argument("--finalize", action="store_true")
    args = ap.parse_args()

    parts_dir = os.path.join(args.state, "parts")
    done_file = os.path.join(args.state, "done.txt")
    os.makedirs(parts_dir, exist_ok=True); os.makedirs(args.workdir, exist_ok=True)
    instruments = [x.strip() for x in args.instruments.split(",") if x.strip()] or None

    if args.finalize:
        parts = sorted(glob.glob(os.path.join(parts_dir, "*.parquet")))
        if not parts:
            raise SystemExit("no parts to finalize")
        bars = pl.concat([pl.read_parquet(p) for p in parts])
        panel = dl.build_price_panel(bars, "close")
        os.makedirs(os.path.dirname(args.cache), exist_ok=True)
        panel.reset_index().to_parquet(args.cache)
        print(f"FINALIZED -> {args.cache} | {panel.shape[0]} bars x {panel.shape[1]} instruments "
              f"({panel.index[0]} -> {panel.index[-1]})")
        return

    done = set(open(done_file).read().split("\n")) - {""} if os.path.exists(done_file) else set()
    _, mem = members(args.zip, instruments, args.start or None, args.end or None)
    total = len(mem)
    todo = [x for x in mem if x[0] not in done]
    if not todo:
        print(f"ALL FILES DONE ({len(done)}/{total}). Run with --finalize."); return

    z = zipfile.ZipFile(args.zip)
    frames, processed, t0 = [], [], time.time()
    for n, sym, d in todo:
        if time.time() - t0 > args.max_seconds:
            break
        z.extract(n, args.workdir); p = os.path.join(args.workdir, n)
        frames.append(fast_bars_1m(p) if args.freq == "1m" else dl.to_bars(dl.load_quotes(p), args.freq))
        os.remove(p); processed.append(n)
    if frames:
        part = os.path.join(parts_dir, f"part_{len(glob.glob(os.path.join(parts_dir,'*.parquet'))):04d}.parquet")
        pl.concat(frames).write_parquet(part)
        open(done_file, "a").write("\n".join(processed) + "\n")
    remaining = len(todo) - len(processed)
    print(f"processed {len(processed)} this run | {len(done)+len(processed)}/{total} total | "
          f"{remaining} remaining ({time.time()-t0:.1f}s)")
    if remaining == 0:
        print("ALL FILES DONE. Run with --finalize.")


if __name__ == "__main__":
    main()
