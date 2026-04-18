"""Generic CSV import utility — parse, validate headers, return rows + errors."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.core.logging import get_logger

log = get_logger(__name__)

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
]


def parse_date(value: str) -> date:
    """Try each supported date format and return the first that parses."""
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {value!r}")


def parse_decimal(value: str) -> Decimal:
    """Parse a decimal string, stripping currency symbols and commas."""
    cleaned = value.strip().replace(",", "").replace("$", "").replace("£", "").replace("€", "")
    if not cleaned:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


async def parse_csv(
    file_content: bytes,
    required_columns: list[str],
    optional_columns: list[str] | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    """Parse CSV bytes into list of row dicts + list of errors.

    Validates required columns exist. Returns (rows, errors).
    Column names are normalised to lowercase/stripped.
    """
    # Decode: try UTF-8 first, fall back to latin-1
    try:
        text = file_content.decode("utf-8-sig")  # handles BOM
    except UnicodeDecodeError:
        text = file_content.decode("latin-1")

    reader = csv.reader(io.StringIO(text))
    all_rows = list(reader)

    if not all_rows:
        return [], ["Empty CSV file"]

    # Normalise headers
    raw_headers = all_rows[0]
    headers = [h.strip().lower() for h in raw_headers]

    # Validate required columns
    missing = [col for col in required_columns if col not in headers]
    if missing:
        return [], [f"Missing required column(s): {', '.join(missing)}"]

    errors: list[str] = []
    rows: list[dict[str, str]] = []

    accepted_columns = set(required_columns)
    if optional_columns:
        accepted_columns.update(optional_columns)

    for row_no, row in enumerate(all_rows[1:], start=2):
        # Skip blank rows
        if not any(cell.strip() for cell in row):
            continue

        row_dict: dict[str, str] = {}
        for idx, header in enumerate(headers):
            if header in accepted_columns and idx < len(row):
                row_dict[header] = row[idx].strip()

        # Validate required columns have values
        empty_required = [col for col in required_columns if not row_dict.get(col)]
        if empty_required:
            errors.append(f"Row {row_no}: missing value for {', '.join(empty_required)}")
            continue

        rows.append(row_dict)

    return rows, errors


def generate_template_csv(
    headers: list[str],
    example_row: list[str] | None = None,
) -> str:
    """Generate a CSV template string with headers and optional example row."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    if example_row:
        writer.writerow(example_row)
    return output.getvalue()
