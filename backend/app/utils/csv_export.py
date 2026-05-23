import csv
from io import StringIO
from typing import Any


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    buffer = StringIO()
    if not rows:
        return ""
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
