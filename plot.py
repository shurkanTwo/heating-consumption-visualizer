from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
OUT.mkdir(exist_ok=True)

COLORS = {
    "R1": "#E69F00",
    "R2": "#0072B2",
    "R3": "#009E73",
    "R4": "#D55E00",
}


def reconstructed_2023_equal(total_weighted_2023):
    heating_months = {1, 2, 3, 4, 10, 11, 12}
    months = pd.date_range("2023-01-31", "2023-12-31", freq="ME")
    per_month = total_weighted_2023 / len(heating_months)
    weighted = [per_month if d.month in heating_months else 0.0 for d in months]
    return pd.DataFrame({"date": months, "weighted": weighted})

def build_label(min_year: int, max_year: int) -> str:
    if min_year == max_year:
        return f"{min_year}"
    if max_year == min_year + 1:
        return f"{min_year}/{str(max_year)[-2:]}"
    return f"{min_year}–{max_year}"

def prepare_increment_series(inc: pd.DataFrame) -> dict:
    df = inc.copy()
    df["increment_weighted"] = df["increment_weighted"].clip(lower=0)
    df = (
        df.groupby(["room", "month"], as_index=False)["increment_weighted"]
        .sum()
        .sort_values(["room", "month"])
    )
    df["date"] = pd.to_datetime(df["month"] + "-01") + pd.offsets.MonthEnd(0)

    min_month = df["date"].min().to_period("M")
    max_month = df["date"].max().to_period("M")
    full_index = pd.period_range(min_month, max_month, freq="M")

    series = {}
    for room in df["room"].unique():
        sub = df[df["room"] == room]
        sub = sub.set_index(sub["date"].dt.to_period("M"))
        sub = sub.reindex(full_index)
        sub["increment_weighted"] = sub["increment_weighted"].fillna(0)
        series[room] = pd.DataFrame(
            {
                "date": full_index.to_timestamp("M"),
                "weighted": sub["increment_weighted"].values,
            }
        )
    return series

def main():
    inc = pd.read_csv(BASE / "data" / "monthly_increments_factor_adjusted.csv")
    totals = pd.read_csv(BASE / "data" / "totals_2023_weighted.csv")

    all_2024plus = prepare_increment_series(inc)
    min_year = int(inc["month"].str.slice(0, 4).min())
    max_year = int(inc["month"].str.slice(0, 4).max())
    span_label = build_label(min_year, max_year)

    # Prepare 2023 baselines
    all_2023 = {}
    for _, r in totals.iterrows():
        all_2023[r["room"]] = reconstructed_2023_equal(float(r["total_weighted_2023"]))

    # Individual room plots
    for room, s2024 in all_2024plus.items():
        plt.figure(figsize=(10, 5))
        plt.plot(
            all_2023[room]["date"],
            all_2023[room]["weighted"],
            linestyle="--",
            color=COLORS.get(room),
            label=f"{room} 2023",
        )
        plt.plot(
            s2024["date"],
            s2024["weighted"],
            marker="o",
            color=COLORS.get(room),
            label=f"{room} {span_label}",
        )
        plt.title(f"Heizverbrauch – {room} (faktorbereinigt)")
        plt.xlabel("Datum")
        plt.ylabel("Verbrauchszuwachs × Faktor (nur positiv)")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend()
        plt.tight_layout()
        plt.savefig(OUT / f"{room}.png", dpi=200)
        plt.close()

    # Combined plot
    plt.figure(figsize=(12, 6))
    for room in sorted(all_2024plus.keys()):
        color = COLORS.get(room)
        plt.plot(
            all_2023[room]["date"],
            all_2023[room]["weighted"],
            linestyle="--",
            color=color,
            label=f"{room} 2023",
        )
        plt.plot(
            all_2024plus[room]["date"],
            all_2024plus[room]["weighted"],
            marker="o",
            color=color,
            label=f"{room} {span_label}",
        )
    plt.title(
        f"Heizverbrauch nach Räumen – Vergleich 2023 vs. {span_label} (faktorbereinigt)"
    )
    plt.xlabel("Datum")
    plt.ylabel("Verbrauchszuwachs × Faktor (nur positiv)")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend(title="Räume / Jahre", ncol=2)
    plt.tight_layout()
    plt.savefig(OUT / "combined.png", dpi=200)
    plt.close()

    print("Wrote plots to:", OUT)


if __name__ == "__main__":
    main()
