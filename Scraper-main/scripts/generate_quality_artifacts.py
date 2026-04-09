from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from pipelines.quality_guard import QualityGuard


def load_records(csv_path: Path) -> list[dict]:
    try:
        df = pd.read_csv(csv_path, engine="python", on_bad_lines="skip", encoding="utf-8", encoding_errors="replace")
        return df.to_dict("records")
    except Exception:
        rows: list[dict] = []
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            for row in reader:
                if not header or len(row) != len(header):
                    continue
                rows.append(dict(zip(header, row)))
        return rows


def main() -> None:
    output_dir = Path("data/output")
    csv_files = sorted(output_dir.glob("scrape_session_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not csv_files:
        print("No scrape_session CSV files found.")
        return

    latest = csv_files[0]
    print(f"Using source file: {latest}")

    records = load_records(latest)
    guard = QualityGuard(output_dir=output_dir)
    seen_hashes: set[str] = set()
    valid, failed, stats = guard.process(records, seen_hashes)

    print(f"Rows seen: {stats['seen']}")
    print(f"Rows valid: {stats['valid']}")
    print(f"Rows dropped: {stats['dropped']}")
    print(f"Rows duplicates: {stats['duplicates']}")
    print("Artifacts generated:")
    print(f"  - {guard.sample_path}")
    print(f"  - {guard.failed_rows_path}")
    print(f"  - {guard.report_path}")

    # Persist a stable 10-row sample file name requested by stakeholders.
    sample_10 = output_dir / "clean_sample_10_rows.json"
    sample_10.write_text(guard.sample_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  - {sample_10}")


if __name__ == "__main__":
    main()
