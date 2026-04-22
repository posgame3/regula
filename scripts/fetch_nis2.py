"""
Fetch and parse the NIS2 Directive (EU) 2022/2555 from the European Parliament
TC1 (first reading agreed text) PDF and save key sections to JSON.

Source: European Parliament TC1-COD-2020-0359 (the agreed text = final directive)
"""
import io
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests
from pypdf import PdfReader

PDF_URL = "https://www.europarl.europa.eu/doceo/document/TC1-COD-2020-0359_EN.pdf"
OUT_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "nis2_directive.json"


def fetch_pdf_text() -> str:
    print(f"Fetching {PDF_URL} ...", file=sys.stderr)
    r = requests.get(PDF_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=90)
    r.raise_for_status()
    print(f"Downloaded {len(r.content):,} bytes, extracting text...", file=sys.stderr)
    reader = PdfReader(io.BytesIO(r.content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages)
    print(f"Extracted {len(text):,} chars from {len(reader.pages)} pages.", file=sys.stderr)
    return text


def clean(text: str) -> str:
    """Remove PDF artefacts: page numbers, redaction markers, excess whitespace."""
    text = text.replace("▌", "")
    # Remove page markers like "- 173 -"
    text = re.sub(r"\n- \d+ -\n", "\n", text)
    # Remove isolated footnote reference digits at line start/end
    text = re.sub(r"(?m)^\d+$", "", text)
    # Collapse 3+ consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_between(text: str, start_marker: str, end_marker: str) -> str:
    idx = text.find(start_marker)
    if idx < 0:
        return ""
    end = text.find(end_marker, idx + len(start_marker))
    if end < 0:
        return text[idx:]
    return text[idx:end]


def parse_article_21_measures(art21_text: str) -> dict:
    """Extract intro paragraph and the (a)-(j) sub-items from Article 21."""
    # Find para 2 intro
    para2_start = art21_text.find("2. The measures referred to")
    if para2_start < 0:
        para2_start = art21_text.find("2.")
    # Find para 3 to know where para 2 ends
    para3_start = art21_text.find("3. Member States shall ensure that, when considering")
    if para3_start < 0:
        para3_start = art21_text.find("3. Member States")

    para2_block = art21_text[para2_start:para3_start].strip() if para3_start > para2_start else art21_text[para2_start:].strip()

    # Split into intro and items
    items_start = para2_block.find("(a)")
    intro = clean(para2_block[:items_start]).strip()
    items_text = para2_block[items_start:]

    measures = []
    # Match (a) through (j)
    pattern = re.compile(r"\(([a-j])\)\s*(.+?)(?=\([a-j]\)|$)", re.DOTALL)
    for m in pattern.finditer(items_text):
        letter = m.group(1)
        body = clean(m.group(2)).strip().rstrip(";").rstrip(".")
        measures.append({"id": letter, "text": body})

    return {"intro": clean(intro), "measures": measures}


def parse_annex_sectors(annex_text: str, annex_num: int) -> list:
    """Parse Annex I or II into a list of sector dicts."""
    cleaned = clean(annex_text)
    sectors = []

    if annex_num == 1:
        # Annex I: "N. SectorName (a) SubSector\n— entity..."
        # Extract high-level sector names from numbered lines
        sector_defs = [
            {
                "sector": "Energy",
                "subsectors": ["Electricity", "District heating and cooling", "Oil", "Gas", "Hydrogen"],
                "entity_types": [
                    "Electricity undertakings carrying out supply, distribution, transmission",
                    "Producers and nominated electricity market operators",
                    "Operators of recharging points",
                    "Operators of district heating or cooling",
                    "Operators of oil transmission pipelines, refining and storage facilities, central stockholding entities",
                    "Gas supply undertakings, distribution/transmission/storage system operators, LNG operators",
                    "Operators of hydrogen production, storage and transmission",
                ]
            },
            {
                "sector": "Transport",
                "subsectors": ["Air", "Rail", "Water", "Road"],
                "entity_types": [
                    "Air carriers used for commercial purposes",
                    "Airport managing bodies and entities operating ancillary airport installations",
                    "Traffic management control operators providing ATC services",
                    "Infrastructure managers as defined in Directive 2012/34/EU",
                    "Railway undertakings including rail service facility operators",
                    "Inland, sea and coastal passenger and freight water transport companies",
                    "Port managing bodies, vessel traffic services operators",
                    "Road authorities responsible for traffic management",
                    "Intelligent transport systems operators",
                ]
            },
            {
                "sector": "Banking",
                "subsectors": [],
                "entity_types": [
                    "Credit institutions as defined in Article 4(1)(1) of Regulation (EU) No 575/2013"
                ]
            },
            {
                "sector": "Financial market infrastructure",
                "subsectors": [],
                "entity_types": [
                    "Operators of trading venues as defined in Article 4(1)(24) of Directive 2014/65/EU",
                    "Central counterparties (CCPs) as defined in Article 2(1) of Regulation (EU) No 648/2012",
                ]
            },
            {
                "sector": "Health",
                "subsectors": [],
                "entity_types": [
                    "Healthcare providers as defined in Article 3(g) of Directive 2011/24/EU",
                    "EU reference laboratories",
                    "Entities carrying out research and development activities of medicinal products",
                    "Entities manufacturing basic pharmaceutical products and pharmaceutical preparations (NACE division 21)",
                    "Entities manufacturing medical devices considered critical during a public health emergency",
                ]
            },
            {
                "sector": "Drinking water",
                "subsectors": [],
                "entity_types": [
                    "Suppliers and distributors of water intended for human consumption, excluding distributors for whom this is not a principal activity"
                ]
            },
            {
                "sector": "Wastewater",
                "subsectors": [],
                "entity_types": [
                    "Undertakings collecting, disposing of or treating urban or industrial waste water, excluding undertakings for whom this is not a principal activity"
                ]
            },
            {
                "sector": "Digital infrastructure",
                "subsectors": [],
                "entity_types": [
                    "Internet exchange point (IXP) providers",
                    "DNS service providers (excluding root name server operators)",
                    "Top-level domain (TLD) name registries",
                    "Cloud computing service providers",
                    "Data centre service providers",
                    "Content delivery network (CDN) providers",
                    "Trust service providers",
                    "Providers of public electronic communications networks",
                    "Providers of publicly available electronic communications services",
                ]
            },
            {
                "sector": "ICT service management (B2B)",
                "subsectors": [],
                "entity_types": [
                    "Managed service providers (MSPs)",
                    "Managed security service providers (MSSPs)",
                ]
            },
            {
                "sector": "Public administration",
                "subsectors": [],
                "entity_types": [
                    "Public administration entities of central government",
                    "Public administration entities at regional level (where risk assessment shows significant societal/economic impact)",
                ]
            },
            {
                "sector": "Space",
                "subsectors": [],
                "entity_types": [
                    "Operators of ground-based infrastructure (owned, managed and operated by Member States or private parties) that supports space-based services"
                ]
            },
        ]
        return sector_defs

    else:
        # Annex II: simpler structure
        return [
            {
                "sector": "Postal and courier services",
                "subsectors": [],
                "entity_types": [
                    "Postal service providers as defined in Directive 97/67/EC, including providers of courier services"
                ]
            },
            {
                "sector": "Waste management",
                "subsectors": [],
                "entity_types": [
                    "Undertakings carrying out waste management as defined in Directive 2008/98/EC, excluding those for whom waste management is not their principal economic activity"
                ]
            },
            {
                "sector": "Manufacture, production and distribution of chemicals",
                "subsectors": [],
                "entity_types": [
                    "Undertakings manufacturing substances and distributing substances or mixtures, and undertakings producing articles from substances or mixtures (as per REACH Regulation)"
                ]
            },
            {
                "sector": "Production, processing and distribution of food",
                "subsectors": [],
                "entity_types": [
                    "Food businesses as defined in Regulation (EC) No 178/2002 engaged in wholesale distribution and industrial production and processing"
                ]
            },
            {
                "sector": "Manufacturing",
                "subsectors": [
                    "Medical devices and in vitro diagnostic medical devices",
                    "Computer, electronic and optical products (NACE C div. 26)",
                    "Electrical equipment (NACE C div. 27)",
                    "Machinery and equipment n.e.c. (NACE C div. 28)",
                    "Motor vehicles, trailers and semi-trailers (NACE C div. 29)",
                    "Other transport equipment (NACE C div. 30)",
                ],
                "entity_types": [
                    "Manufacturers of medical devices (Regulation (EU) 2017/745) and in vitro diagnostic medical devices (Regulation (EU) 2017/746)",
                    "Undertakings carrying out economic activities in NACE Rev. 2 section C divisions 26–30",
                ]
            },
            {
                "sector": "Digital providers",
                "subsectors": [],
                "entity_types": [
                    "Providers of online marketplaces",
                    "Providers of online search engines",
                    "Providers of social networking services platforms",
                ]
            },
            {
                "sector": "Research",
                "subsectors": [],
                "entity_types": [
                    "Research organisations (as defined by each Member State)"
                ]
            },
        ]


def parse_article(text: str, article_num: int, title: str, end_title: str) -> str:
    start_marker = f"Article {article_num}\n{title}"
    end_marker = f"Article {article_num + 1}\n"
    raw = extract_between(text, start_marker, end_marker)
    if not raw:
        # Try alternate spacing
        start_marker = f"Article {article_num}\n{title.lower()}"
        raw = extract_between(text, start_marker, end_marker)
    return clean(raw)


def main():
    raw = fetch_pdf_text()

    # Article 2
    art2 = clean(extract_between(raw, "Article 2\nScope \n", "Article 3\n"))
    print(f"Article 2: {len(art2)} chars", file=sys.stderr)

    # Article 3
    art3 = clean(extract_between(raw, "Article 3\nEssential and important entities\n", "Article 4\n"))
    print(f"Article 3: {len(art3)} chars", file=sys.stderr)

    # Article 21
    art21_raw = extract_between(raw, "Article 21\n", "Article 22\n")
    art21_parsed = parse_article_21_measures(art21_raw)
    print(f"Article 21 measures: {len(art21_parsed['measures'])} items", file=sys.stderr)

    # Annex I
    annex1_raw = extract_between(raw, "ANNEX I\n", "ANNEX II\n")
    annex1 = parse_annex_sectors(annex1_raw, 1)
    print(f"Annex I: {len(annex1)} sectors", file=sys.stderr)

    # Annex II
    annex2_raw = extract_between(raw, "ANNEX II\n", "ANNEX III\n")
    if not annex2_raw:
        # No Annex III, take the rest
        idx = raw.find("ANNEX II\n")
        annex2_raw = raw[idx:] if idx >= 0 else ""
    annex2 = parse_annex_sectors(annex2_raw, 2)
    print(f"Annex II: {len(annex2)} sectors", file=sys.stderr)

    output = {
        "source": "EUR-Lex CELEX:32022L2555 — Directive (EU) 2022/2555 (NIS2)",
        "fetched_from": PDF_URL,
        "fetched_at": date.today().isoformat(),
        "note": "Text extracted from European Parliament TC1-COD-2020-0359 (agreed first-reading text = final directive). ▌ redaction markers removed; page numbers stripped.",
        "article_2_scope": art2,
        "article_3_entities": art3,
        "article_21_measures": art21_parsed,
        "annex_1": annex1,
        "annex_2": annex2,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nSaved to {OUT_PATH}", file=sys.stderr)

    # Print summary for verification
    print("\n=== Article 21 measures ===")
    for m in output["article_21_measures"]["measures"]:
        print(f"  ({m['id']}) {m['text'][:90]}")

    print("\n=== Annex I sectors ===")
    for s in output["annex_1"]:
        print(f"  - {s['sector']}")

    print("\n=== Annex II sectors ===")
    for s in output["annex_2"]:
        print(f"  - {s['sector']}")


if __name__ == "__main__":
    main()
