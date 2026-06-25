"""
Load the Week-1 backtest Parquet and turn it into clean price bars.

The real file is ~20GB of quotes across 30+ instruments, so we use polars'
lazy scanner: filter / resample happen before anything is pulled into memory.

We do NOT know the exact column names yet. Run `inspect_parquet(path)` on the
real file first; it prints the schema and a sample. The alias maps below cover
the common namings -- add to them if your file uses something different.
"""
from __future__ import annotations

import polars as pl

# Candidate column names, in priority order. Matching is case-insensitive.
TS_ALIASES = ["timestamp", "time", "ts", "datetime", "date_time", "dt", "epoch", "t"]
SYMBOL_ALIASES = ["symbol", "sym", "instrument", "pair", "ticker", "asset", "market", "name"]
BID_ALIASES = ["bid", "bid_price", "best_bid"]
ASK_ALIASES = ["ask", "ask_price", "best_ask", "offer"]
PRICE_ALIASES = ["mid", "price", "close", "last", "px", "mid_price"]
VOLUME_ALIASES = ["volume", "vol", "size", "qty", "quantity"]


def _match(schema_names: list[str], aliases: list[str]) -> str | None:
    lower = {n.lower(): n for n in schema_names}
    for a in aliases:
        if a in lower:
            return lower[a]
    # loose contains-match as a fallback
    for a in aliases:
        for ln, orig in lower.items():
            if a in ln:
                return orig
    return None


def detect_columns(schema_names: list[str]) -> dict[str, str | None]:
    """Best-effort map of file columns -> canonical names."""
    return {
        "ts": _match(schema_names, TS_ALIASES),
        "symbol": _match(schema_names, SYMBOL_ALIASES),
        "bid": _match(schema_names, BID_ALIASES),
        "ask": _match(schema_names, ASK_ALIASES),
        "price": _match(schema_names, PRICE_ALIASES),
        "volume": _match(schema_names, VOLUME_ALIASES),
    }


def inspect_parquet(path: str, n: int = 5) -> dict:
    """Print schema, row count, detected columns and a sample. Run this FIRST."""
    lf = pl.scan_parquet(path)
    schema = lf.collect_schema()
    names = list(schema.names())
    n_rows = lf.select(pl.len()).collect().item()
    sample = lf.head(n).collect()
    mapping = detect_columns(names)

    print(f"\n=== {path} ===")
    print(f"rows: {n_rows:,}")
    print("\ncolumns:")
    for name in names:
        print(f"  {name:<22} {schema[name]}")
    print("\ndetected mapping (canonical -> file column):")
    for k, v in mapping.items():
        flag = "" if v else "   <-- NOT FOUND, set manually"
        print(f"  {k:<8} -> {v}{flag}")
    print("\nsample rows:")
    print(sample)
    return {"n_rows": n_rows, "columns": names, "schema": schema, "mapping": mapping}


def load_quotes(
    path: str,
    instruments: list[str] | None = None,
    start=None,
    end=None,
    mapping: dict[str, str] | None = None,
) -> pl.DataFrame:
    """
    Return a normalized frame: [ts (Datetime), symbol (str), bid, ask, mid].

    `mapping` overrides auto-detection (pass the dict from inspect_parquet and
    edit any None entries). `instruments`, `start`, `end` push filters down to
    the scan so the 20GB file is never fully materialized.
    """
    lf = pl.scan_parquet(path)
    names = list(lf.collect_schema().names())
    m = mapping or detect_columns(names)

    if not m.get("ts") or not m.get("symbol"):
        raise ValueError(
            f"Could not locate timestamp/symbol columns. Detected={m}. "
            "Run inspect_parquet() and pass an explicit `mapping=`."
        )

    ts, sym = m["ts"], m["symbol"]
    exprs = [pl.col(ts).alias("ts_src"), pl.col(sym).cast(pl.Utf8).alias("symbol")]
    has_quotes = bool(m.get("bid") and m.get("ask"))
    if has_quotes:
        exprs += [pl.col(m["bid"]).cast(pl.Float64).alias("bid"),
                  pl.col(m["ask"]).cast(pl.Float64).alias("ask")]
    elif m.get("price"):
        exprs += [pl.col(m["price"]).cast(pl.Float64).alias("mid")]
    else:
        raise ValueError(f"No bid/ask or price column found. Detected={m}.")

    lf = lf.select(exprs)
    if has_quotes:
        lf = lf.with_columns(((pl.col("bid") + pl.col("ask")) / 2).alias("mid"))
    else:
        lf = lf.with_columns([pl.col("mid").alias("bid"), pl.col("mid").alias("ask")])

    # Normalize timestamp into a single 'ts' column (datetime / epoch / string).
    lf = _parse_ts(lf, "ts_src")

    if instruments:
        lf = lf.filter(pl.col("symbol").is_in(instruments))
    if start is not None:
        lf = lf.filter(pl.col("ts") >= pl.lit(start))
    if end is not None:
        lf = lf.filter(pl.col("ts") <= pl.lit(end))

    return lf.select(["ts", "symbol", "bid", "ask", "mid"]).sort(["symbol", "ts"]).collect()


def _parse_ts(lf: pl.LazyFrame, col: str) -> pl.LazyFrame:
    """Return `lf` with a normalized Datetime column 'ts', dropping `col`."""
    dtype = lf.collect_schema()[col]
    if dtype == pl.Datetime:
        return lf.rename({col: "ts"})
    if dtype in (pl.Int64, pl.Int32, pl.UInt64, pl.UInt32, pl.Float64):
        # Guess the epoch unit by the magnitude of the first value.
        first = lf.select(pl.col(col).drop_nulls().first()).collect().item()
        v = abs(float(first or 0))
        unit = "s" if v < 1e11 else "ms" if v < 1e14 else "us" if v < 1e17 else "ns"
        return lf.with_columns(
            pl.from_epoch(pl.col(col).cast(pl.Int64), time_unit=unit).alias("ts")
        ).drop(col)
    return lf.with_columns(
        pl.col(col).str.to_datetime(strict=False).alias("ts")
    ).drop(col)


def to_bars(quotes: pl.DataFrame, freq: str = "1m") -> pl.DataFrame:
    """
    Resample normalized quotes to OHLC bars per symbol.
    `freq` uses polars duration strings: '1m', '5m', '15m', '1h', etc.
    Returns long format: [ts, symbol, open, high, low, close, mean_spread].
    """
    return (
        quotes.sort("ts")
        .group_by_dynamic("ts", every=freq, group_by="symbol")
        .agg(
            pl.col("mid").first().alias("open"),
            pl.col("mid").max().alias("high"),
            pl.col("mid").min().alias("low"),
            pl.col("mid").last().alias("close"),
            (pl.col("ask") - pl.col("bid")).mean().alias("mean_spread"),
        )
        .sort(["symbol", "ts"])
    )


def build_price_panel(bars: pl.DataFrame, field: str = "close"):
    """
    Pivot long bars to a wide pandas DataFrame: index=ts, columns=symbol, values=close.
    Forward-fills gaps (e.g. when one market trades while another is closed).
    Returns a pandas DataFrame -- convenient for vectorized strategy math.
    """
    wide = bars.pivot(values=field, index="ts", on="symbol", aggregate_function="last")
    pdf = wide.sort("ts").to_pandas().set_index("ts").sort_index()
    return pdf.ffill().dropna(how="all")
