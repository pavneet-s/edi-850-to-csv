# EDI 850 to CSV

A small Python tool that reads ANSI X12 850 purchase orders and writes the line items to a CSV file that opens in Excel. It also checks the file's envelope and counts, the kind of checks used when a transmission fails or a trading partner says an order is missing.

Standard library only (Python 3.8+), no installs needed.

## Run it

```
python edi850_to_csv.py samples/sample_850.edi -o purchase_orders.csv
```

```
Wrote 5 line(s) from 2 PO(s) to purchase_orders.csv
```

Try the broken file to see the checks:

```
python edi850_to_csv.py samples/bad_850.edi -o bad.csv
```

```
ERROR: PO PO45004: SE01 says 12 segments, counted 14
ERROR: PO PO45004: CTT01 says 3 lines, found 2 PO1 lines
ERROR: GE02 103 does not match GS06 102
```

The exit code is 1 when any check fails, so the script can be used in a batch job.

## What it reads

| Segment | Meaning | CSV column |
|---|---|---|
| ISA / IEA | Interchange envelope, separators, control number | checks only |
| GS / GE | Functional group (GS01 = PO) | checks only |
| ST / SE | One 850 transaction set | checks only |
| BEG | PO type, PO number, PO date | po_type, po_number, po_date |
| DTM*002 | Requested delivery date | requested_delivery |
| N1*BY / N1*ST | Buyer and ship-to names | buyer, ship_to |
| PO1 | Line number, quantity, unit of measure, price, part numbers (BP, VP, UP) | line, quantity, uom, unit_price, buyer_part, vendor_part, upc |
| PID | Item description | description |
| CTT | Number of PO1 lines | checks only |

`line_total` is calculated as quantity times unit price.

## Checks

- ISA13 matches IEA02, GS06 matches GE02, ST02 matches SE02
- IEA01 group count, GE01 transaction count and SE01 segment count are correct
- CTT01 matches the number of PO1 lines
- GS01 is PO and ST01 is 850
- Quantities and prices are numbers
- The file ends with IEA (catches cut-off transmissions)

Separators are read from the ISA segment, so files that use `|` or `'` instead of `*` and `~` also work.

## Tests

```
python -m unittest -v
```

## Sample data

The files in `samples/` are made up for testing and do not belong to any real company.
