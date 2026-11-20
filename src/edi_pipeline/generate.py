"""Generate fake X12 850 (purchase order) and 810 (invoice) files, with injected errors."""
import json
import random
from datetime import date, timedelta
from pathlib import Path

ELEMENT_SEP = "*"
SEGMENT_END = "~"
COMPONENT_SEP = ":"

PARTNERS = {
    "NORTHWIND01": "Northwind Supply Co",
    "BLUERIDGE02": "Blue Ridge Wholesale",
    "SMOKYMTN03": "Smoky Mountain Foods",
    "TENNRIVER04": "Tennessee River Goods",
    "CUMBERLND05": "Cumberland Distributors",
    "VOLUNTEER06": "Volunteer Hardware",
}
ITEMS = [(f"SKU{n:04d}", round(random.Random(n).uniform(2.5, 90.0), 2)) for n in range(1, 21)]
SENDER = "FAKEVENDOR"  # our fictional company

ERROR_TYPES = {
    "850": ["missing_segment", "duplicate_control", "bad_se_count", "bad_date"],
    "810": ["bad_total", "missing_segment", "duplicate_control", "bad_se_count", "bad_date"],
}


def pad(value: str, width: int) -> str:
    return value.ljust(width)[:width]


def isa(sender: str, receiver: str, control: int, d: date, usage: str = "T") -> str:
    parts = ["ISA", "00", pad("", 10), "00", pad("", 10), "ZZ", pad(sender, 15), "ZZ",
             pad(receiver, 15), d.strftime("%y%m%d"), "0930", "^", "00501",
             f"{control:09d}", "0", usage, COMPONENT_SEP]
    return ELEMENT_SEP.join(parts)


def build_850(po_number: str, order_date: date, lines: list) -> list:
    segs = ["ST*850*0001", f"BEG*00*SA*{po_number}**{order_date:%Y%m%d}"]
    for i, (sku, qty, price) in enumerate(lines, 1):
        segs.append(f"PO1*{i}*{qty}*EA*{price:.2f}**VP*{sku}")
    segs.append(f"CTT*{len(lines)}")
    segs.append(f"SE*{len(segs) + 1}*0001")
    return segs


def build_810(invoice_number: str, po_number: str, inv_date: date, lines: list) -> list:
    segs = ["ST*810*0001", f"BIG*{inv_date:%Y%m%d}*{invoice_number}**{po_number}"]
    total_cents = 0
    for i, (sku, qty, price) in enumerate(lines, 1):
        segs.append(f"IT1*{i}*{qty}*EA*{price:.2f}**VP*{sku}")
        total_cents += round(qty * price * 100)
    segs.append(f"TDS*{total_cents}")  # implied two decimals
    segs.append(f"CTT*{len(lines)}")
    segs.append(f"SE*{len(segs) + 1}*0001")
    return segs


def wrap_interchange(sender, receiver, control, d, tx_segments, tx_code):
    gs_code = {"850": "PO", "810": "IN"}[tx_code]
    body = [f"GS*{gs_code}*{sender}*{receiver}*{d:%Y%m%d}*0930*{control}*X*005010",
            *tx_segments, f"GE*1*{control}"]
    return [isa(sender, receiver, control, d), *body, f"IEA*1*{control:09d}"]


def inject_error(segments: list, error: str, used_controls: list) -> list:
    segs = list(segments)
    if error == "bad_total":
        for i, s in enumerate(segs):
            if s.startswith("TDS*"):
                segs[i] = f"TDS*{int(s.split('*')[1]) + random.randint(100, 5000)}"
    elif error == "missing_segment":
        for i, s in enumerate(segs):
            if s.startswith(("BEG*", "BIG*")):
                del segs[i]
                break
    elif error == "bad_se_count":
        for i, s in enumerate(segs):
            if s.startswith("SE*"):
                _, count, ctrl = s.split("*")
                segs[i] = f"SE*{int(count) + 2}*{ctrl}"
    elif error == "bad_date":
        for i, s in enumerate(segs):
            if s.startswith(("BEG*", "BIG*")):
                parts = s.split("*")
                idx = 5 if parts[0] == "BEG" else 1
                parts[idx] = "20261340"  # not a real date
                segs[i] = "*".join(parts)
    return segs


def generate(out_dir: Path, run_date: date, n_pairs: int = 40, error_rate: float = 0.15, seed: int = 42):
    random.seed(seed + run_date.toordinal())
    day_dir = out_dir / run_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    control = random.randint(100000, 400000)
    used_controls = []
    seq = 0
    for n in range(n_pairs):
        partner = random.choice(list(PARTNERS))
        po_number = f"PO{run_date:%y%m%d}{n:04d}"
        lines = [(sku, random.randint(1, 40), price) for sku, price in random.sample(ITEMS, random.randint(1, 5))]
        for tx_code, builder in (("850", build_850), ("810", build_810)):
            control += 1
            d = run_date - timedelta(days=random.randint(0, 2))
            if tx_code == "850":
                tx = builder(po_number, d, lines)
            else:
                tx = builder(f"INV{po_number[2:]}", po_number, d, lines)
            used = control
            error = None
            if random.random() < error_rate:
                error = random.choice(ERROR_TYPES[tx_code])
                same_partner = [c for p, c in used_controls if p == partner]
                if error == "duplicate_control" and same_partner:
                    used = random.choice(same_partner)
                else:
                    error = error if error != "duplicate_control" else None
                    if error:
                        tx = inject_error(tx, error, used_controls)
            used_controls.append((partner, control))
            segs = wrap_interchange(partner, SENDER, used, d, tx, tx_code)
            seq += 1
            name = f"{seq:04d}_{partner}_{tx_code}.edi"  # sequence prefix = arrival order
            (day_dir / name).write_text(SEGMENT_END.join(segs) + SEGMENT_END, encoding="ascii")
            manifest.append({"file": name, "partner": partner, "type": tx_code, "injected_error": error})
    (day_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2))
    return day_dir, manifest


if __name__ == "__main__":
    day_dir, manifest = generate(Path("data/landing"), date.today())
    bad = sum(1 for m in manifest if m["injected_error"])
    print(f"Wrote {len(manifest)} files to {day_dir} ({bad} with injected errors)")
