"""Convert X12 850 purchase orders into a CSV file and check the file for errors.

Usage:
    python edi850_to_csv.py samples/sample_850.edi -o purchase_orders.csv

How an X12 file is laid out:
    ISA ... IEA   interchange envelope (one per file)
      GS ... GE   functional group (one or more per interchange)
        ST ... SE transaction set, here an 850 purchase order (one or more per group)

Each segment ends with a segment terminator (often ~) and its elements are split
by an element separator (often *). Both are read from the fixed-width ISA segment,
so the script works with whatever separators the trading partner uses.
"""

import argparse
import csv
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

CSV_COLUMNS = [
    "po_number", "po_date", "po_type", "buyer", "ship_to", "requested_delivery",
    "line", "quantity", "uom", "unit_price", "line_total",
    "buyer_part", "vendor_part", "upc", "description",
]

# Product ID qualifiers used in PO1 and the CSV column each one fills.
PART_QUALIFIERS = {"BP": "buyer_part", "VP": "vendor_part", "UP": "upc"}

PO_TYPES = {"SA": "Stand-alone order", "BK": "Blanket order", "RL": "Release"}


def read_segments(text):
    """Split raw X12 text into a list of segments, each a list of elements."""
    text = text.lstrip("﻿ \r\n\t")
    if not text.startswith("ISA") or len(text) < 106:
        raise ValueError("File does not start with a complete ISA segment")

    # The ISA segment is always 106 characters long, so the separators sit at
    # fixed positions: element separator at 3, segment terminator at 105.
    element_sep = text[3]
    segment_end = text[105]

    segments = []
    for raw in text.split(segment_end):
        raw = raw.strip("\r\n\t ")
        if raw:
            segments.append(raw.split(element_sep))
    return segments


def element(segment, position):
    """Return element n of a segment (1-based like the X12 spec), or '' if missing."""
    return segment[position].strip() if position < len(segment) else ""


def format_date(ccyymmdd):
    try:
        return datetime.strptime(ccyymmdd, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return ccyymmdd


def to_decimal(value, label, errors):
    try:
        return Decimal(value)
    except InvalidOperation:
        errors.append(f"{label}: '{value}' is not a number")
        return Decimal(0)


def parse_850(segments):
    """Walk the segments, build CSV rows and collect any validation errors."""
    rows, errors = [], []
    isa_control = gs_control = st_control = None
    group_count = transaction_count = 0
    segments_in_transaction = 0
    header = {}
    line_count = 0
    ctt_count = None
    current_line = None

    for seg in segments:
        tag = seg[0]
        if segments_in_transaction:
            segments_in_transaction += 1

        if tag == "ISA":
            isa_control = element(seg, 13)
        elif tag == "GS":
            group_count += 1
            transaction_count = 0
            gs_control = element(seg, 6)
            if element(seg, 1) != "PO":
                errors.append(f"GS01 is '{element(seg, 1)}', expected PO for purchase orders")
        elif tag == "ST":
            transaction_count += 1
            st_control = element(seg, 2)
            segments_in_transaction = 1
            header, line_count, ctt_count, current_line = {}, 0, None, None
            if element(seg, 1) != "850":
                errors.append(f"ST {st_control}: transaction type is {element(seg, 1)}, not 850")
        elif tag == "BEG":
            header["po_type"] = PO_TYPES.get(element(seg, 2), element(seg, 2))
            header["po_number"] = element(seg, 3)
            header["po_date"] = format_date(element(seg, 5))
        elif tag == "DTM" and element(seg, 1) == "002":
            header["requested_delivery"] = format_date(element(seg, 2))
        elif tag == "N1" and element(seg, 1) == "BY":
            header["buyer"] = element(seg, 2)
        elif tag == "N1" and element(seg, 1) == "ST":
            header["ship_to"] = element(seg, 2)
        elif tag == "PO1":
            line_count += 1
            label = f"PO {header.get('po_number', '?')} line {element(seg, 1)}"
            qty = to_decimal(element(seg, 2), f"{label} quantity", errors)
            price = to_decimal(element(seg, 4), f"{label} unit price", errors)
            current_line = {
                **header,
                "line": element(seg, 1),
                "quantity": qty,
                "uom": element(seg, 3),
                "unit_price": price,
                "line_total": (qty * price).quantize(Decimal("0.01")),
            }
            # Product IDs come in qualifier/value pairs starting at PO106.
            for pos in range(6, len(seg) - 1, 2):
                column = PART_QUALIFIERS.get(element(seg, pos))
                if column:
                    current_line[column] = element(seg, pos + 1)
            rows.append(current_line)
        elif tag == "PID" and current_line is not None:
            current_line["description"] = element(seg, 5)
        elif tag == "CTT":
            ctt_count = element(seg, 1)
        elif tag == "SE":
            if element(seg, 2) != st_control:
                errors.append(f"SE02 {element(seg, 2)} does not match ST02 {st_control}")
            if element(seg, 1) != str(segments_in_transaction):
                errors.append(
                    f"PO {header.get('po_number', '?')}: SE01 says {element(seg, 1)} segments, "
                    f"counted {segments_in_transaction}")
            if ctt_count is not None and ctt_count != str(line_count):
                errors.append(
                    f"PO {header.get('po_number', '?')}: CTT01 says {ctt_count} lines, "
                    f"found {line_count} PO1 lines")
            segments_in_transaction = 0
        elif tag == "GE":
            if element(seg, 2) != gs_control:
                errors.append(f"GE02 {element(seg, 2)} does not match GS06 {gs_control}")
            if element(seg, 1) != str(transaction_count):
                errors.append(f"GE01 says {element(seg, 1)} transactions, counted {transaction_count}")
        elif tag == "IEA":
            if element(seg, 2) != isa_control:
                errors.append(f"IEA02 {element(seg, 2)} does not match ISA13 {isa_control}")
            if element(seg, 1) != str(group_count):
                errors.append(f"IEA01 says {element(seg, 1)} groups, counted {group_count}")

    if segments and segments[-1][0] != "IEA":
        errors.append("File ends without an IEA segment (transmission may be cut off)")
    return rows, errors


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert X12 850 purchase orders to CSV.")
    parser.add_argument("input", help="X12 850 file to read")
    parser.add_argument("-o", "--output", default="purchase_orders.csv", help="CSV file to write")
    args = parser.parse_args(argv)

    with open(args.input, encoding="utf-8") as f:
        segments = read_segments(f.read())
    rows, errors = parse_850(segments)
    write_csv(rows, args.output)

    po_numbers = sorted({row.get("po_number", "") for row in rows})
    print(f"Wrote {len(rows)} line(s) from {len(po_numbers)} PO(s) to {args.output}")
    for message in errors:
        print(f"ERROR: {message}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
