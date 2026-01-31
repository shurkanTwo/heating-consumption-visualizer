from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class SwapWindow:
    start: date
    end: date
    value: float
    source: str


def load_readings(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing readings CSV: {path}")
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    if "meter_id" not in df.columns:
        df["meter_id"] = "single"
    if "comment" not in df.columns:
        df["comment"] = ""
    return df


def generate_reconstruction_window(room_df: pd.DataFrame) -> SwapWindow | None:
    if room_df["meter_id"].nunique() < 2:
        return None

    old_df = room_df[room_df["meter_id"] != "new"].sort_values("date")
    new_df = room_df[room_df["meter_id"] == "new"].sort_values("date")
    if old_df.empty or new_df.empty:
        return None

    last_old_date = old_df["date"].max().date()
    first_new_row = new_df.iloc[0]
    first_new_date = first_new_row["date"].date()
    first_new_value = float(first_new_row["reading"])

    if first_new_date <= last_old_date:
        return None

    start = last_old_date + timedelta(days=1)
    end = first_new_date
    source = f"reconstructed_from_meter_swap_{int(first_new_value)}_to_{end.isoformat()}"
    return SwapWindow(start=start, end=end, value=first_new_value, source=source)


def allocate_by_days(window: SwapWindow) -> dict[str, float]:
    total_days = (window.end - window.start).days + 1
    if total_days <= 0:
        return {}

    allocations: dict[str, float] = {}
    cursor = window.start
    while cursor <= window.end:
        month_end = (pd.Timestamp(cursor).to_period("M").to_timestamp("M")).date()
        seg_end = min(month_end, window.end)
        days = (seg_end - cursor).days + 1
        month_key = f"{cursor.year:04d}-{cursor.month:02d}"
        allocations[month_key] = allocations.get(month_key, 0.0) + window.value * days / total_days
        cursor = seg_end + timedelta(days=1)
    return allocations


def measured_increments(room_df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for meter_id, g in room_df.groupby("meter_id"):
        g = g.sort_values("date")
        g["diff"] = g["reading"].diff()
        g["pos_diff"] = g["diff"].clip(lower=0)
        for _, r in g.iterrows():
            if pd.isna(r["pos_diff"]):
                continue
            rows.append(
                {
                    "month": r["date"].to_period("M").strftime("%Y-%m"),
                    "increment_raw": float(r["pos_diff"]),
                    "source": f"measured_{meter_id}",
                }
            )
    return rows


def build_monthly_increments(readings: pd.DataFrame) -> pd.DataFrame:
    out_rows: list[dict] = []

    for room in readings["room"].drop_duplicates().tolist():
        room_df = readings[readings["room"] == room].copy()

        # Exclude cutoff values from increments (display-only, not a new reading).
        room_df = room_df[~room_df["comment"].astype(str).str.contains("cutoff", case=False, na=False)]

        factor = float(room_df["factor"].iloc[0])

        for row in measured_increments(room_df):
            out_rows.append(
                {
                    "room": room,
                    "month": row["month"],
                    "increment_raw": row["increment_raw"],
                    "increment_weighted": row["increment_raw"] * factor,
                    "source": row["source"],
                }
            )

        window = generate_reconstruction_window(room_df)
        if window:
            for month, value in allocate_by_days(window).items():
                out_rows.append(
                    {
                        "room": room,
                        "month": month,
                        "increment_raw": value,
                        "increment_weighted": value * factor,
                        "source": window.source,
                    }
                )

    df = pd.DataFrame(out_rows)
    df = df.sort_values(["room", "month", "source"]).reset_index(drop=True)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build monthly_increments_factor_adjusted.csv from readings."
    )
    parser.add_argument(
        "--readings",
        default="data/readings_2023-2026.csv",
        help="Path to readings CSV",
    )
    parser.add_argument(
        "--out",
        default="data/monthly_increments_factor_adjusted.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    readings = load_readings(Path(args.readings))
    out = build_monthly_increments(readings)
    out_path = Path(args.out)
    out.to_csv(out_path, index=False, float_format="%.6f")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
