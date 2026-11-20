"""Generate today's fake files and load them into DuckDB, without Dagster."""
from datetime import date
from pathlib import Path

from edi_pipeline.generate import generate
from edi_pipeline.load import load_day

if __name__ == "__main__":
    landing = Path("data/landing")
    day_dir, manifest = generate(landing, date.today())
    print(f"Generated {len(manifest)} files in {day_dir}")
    print(load_day(Path("data/warehouse.duckdb"), day_dir))
