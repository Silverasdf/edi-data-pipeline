"""Parse and validate X12 850 and 810 files. Valid files become rows; invalid ones become rejects."""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ParsedFile:
    file_name: str
    partner: str = ""
    tx_type: str = ""
    control_number: str = ""
    doc_number: str = ""      # PO number (850) or invoice number (810)
    po_number: str = ""
    doc_date: str = ""
    total_cents: int | None = None
    lines: list = field(default_factory=list)  # (line_no, qty, unit_price, sku)
    errors: list = field(default_factory=list)  # (error_code, detail)


def split_segments(raw: str):
    # ISA is fixed width: element separator is character 4, segment terminator is character 106.
    elem, term = raw[3], raw[105]
    return [s.split(elem) for s in raw.split(term) if s.strip()], elem


def parse_file(path: Path) -> ParsedFile:
    pf = ParsedFile(file_name=path.name)
    raw = path.read_text(encoding="ascii", errors="replace").strip()
    if not raw.startswith("ISA") or len(raw) < 106:
        pf.errors.append(("NOT_X12", "File does not start with a complete ISA segment"))
        return pf
    segs, _ = split_segments(raw)
    by_id = {}
    for s in segs:
        by_id.setdefault(s[0], []).append(s)

    isa = by_id["ISA"][0]
    pf.partner, pf.control_number = isa[6].strip(), isa[13]

    st = by_id.get("ST", [None])[0]
    if st is None:
        pf.errors.append(("MISSING_ST", "No ST segment"))
        return pf
    pf.tx_type = st[1]

    # Envelope checks
    se = by_id.get("SE", [None])[0]
    if se is None:
        pf.errors.append(("MISSING_SE", "No SE segment"))
    else:
        st_index = next(i for i, s in enumerate(segs) if s[0] == "ST")
        se_index = next(i for i, s in enumerate(segs) if s[0] == "SE")
        actual = se_index - st_index + 1
        if int(se[1]) != actual:
            pf.errors.append(("BAD_SE_COUNT", f"SE says {se[1]} segments, found {actual}"))
        if se[2] != st[2]:
            pf.errors.append(("SE_CONTROL_MISMATCH", f"ST {st[2]} vs SE {se[2]}"))
    iea = by_id.get("IEA", [None])[0]
    if iea is None or iea[2] != pf.control_number:
        pf.errors.append(("IEA_CONTROL_MISMATCH", "IEA control number missing or different from ISA13"))

    # Header segment: BEG for 850, BIG for 810
    header_id, line_id = ("BEG", "PO1") if pf.tx_type == "850" else ("BIG", "IT1")
    if pf.tx_type not in ("850", "810"):
        pf.errors.append(("UNSUPPORTED_TYPE", f"Transaction set {pf.tx_type}"))
        return pf
    header = by_id.get(header_id, [None])[0]
    if header is None:
        pf.errors.append(("MISSING_HEADER", f"No {header_id} segment"))
        return pf
    if pf.tx_type == "850":
        pf.doc_number, pf.po_number, pf.doc_date = header[3], header[3], header[5]
    else:
        pf.doc_date, pf.doc_number, pf.po_number = header[1], header[2], header[4]
    try:
        datetime.strptime(pf.doc_date, "%Y%m%d")
    except ValueError:
        pf.errors.append(("BAD_DATE", f"{pf.doc_date} is not a valid YYYYMMDD date"))

    # Line items
    for s in by_id.get(line_id, []):
        pf.lines.append((int(s[1]), int(s[2]), float(s[4]), s[7]))
    ctt = by_id.get("CTT", [None])[0]
    if ctt and int(ctt[1]) != len(pf.lines):
        pf.errors.append(("BAD_LINE_COUNT", f"CTT says {ctt[1]} lines, found {len(pf.lines)}"))

    # Invoice total check (TDS has two implied decimals)
    if pf.tx_type == "810":
        tds = by_id.get("TDS", [None])[0]
        if tds:
            pf.total_cents = int(tds[1])
            expected = sum(round(q * p * 100) for _, q, p, _ in pf.lines)
            if pf.total_cents != expected:
                pf.errors.append(("BAD_TOTAL", f"TDS {pf.total_cents} vs lines {expected} (cents)"))
        else:
            pf.errors.append(("MISSING_TDS", "No TDS segment"))
    return pf


def parse_directory(day_dir: Path) -> list:
    return [parse_file(p) for p in sorted(day_dir.glob("*.edi"))]
