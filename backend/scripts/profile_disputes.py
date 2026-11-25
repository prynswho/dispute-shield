"""Print aggregate date and outcome counts for a local disputes CSV."""

import argparse
from pathlib import Path

import pandas as pd


OUTCOMES = ["won", "lost"]
DATE_COLUMNS = ["opened_at", "closed_at"]


def print_profile(csv_path: Path) -> None:
    disputes = pd.read_csv(
        csv_path, usecols=["outcome", *DATE_COLUMNS], dtype="string", keep_default_na=False
    )
    disputes["outcome"] = disputes["outcome"].str.strip().str.lower()
    resolved = disputes.loc[disputes["outcome"].isin(OUTCOMES)].copy()

    print(f"Won/lost rows: {len(resolved):,} of {len(disputes):,}")
    outcomes = resolved["outcome"].value_counts().reindex(OUTCOMES, fill_value=0)
    print(outcomes.to_string())

    date_issues = {}
    for column in DATE_COLUMNS:
        raw = resolved[column].str.strip()
        missing = raw.eq("")
        parsed = pd.to_datetime(raw, format="mixed", errors="coerce", utc=True)
        date_issues[column] = {
            "missing": int(missing.sum()),
            "invalid": int((parsed.isna() & ~missing).sum()),
        }
        resolved[column] = parsed

    print("\nDate issues among won/lost rows")
    print(pd.DataFrame.from_dict(date_issues, orient="index").to_string())
    closed_before_open = resolved["closed_at"].lt(resolved["opened_at"]).sum()
    print(f"Closed before opened: {closed_before_open:,}")

    opened_month = resolved["opened_at"].dt.strftime("%Y-%m").rename("opened_month")
    by_month = pd.crosstab(opened_month, resolved["outcome"]).reindex(
        columns=OUTCOMES, fill_value=0
    )
    by_month["total"] = by_month[OUTCOMES].sum(axis=1)
    print("\nWon/lost rows by opened month (UTC)")
    print(by_month.to_string() if not by_month.empty else "No valid opening dates.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Path to the local disputes CSV")
    args = parser.parse_args()
    print_profile(args.csv_path)
