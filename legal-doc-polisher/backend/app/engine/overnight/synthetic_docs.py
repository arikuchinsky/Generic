"""Synthetic Legal Document Generator for testing.

Generates realistic CRE legal documents with intentional formatting
inconsistencies, so the polisher can be tested end-to-end without
needing external document sources like EDGAR.

Each document has randomized formatting "bugs" that the polisher
should detect and fix:
- Mixed fonts in headings
- Inconsistent heading bold/underline
- Straight quotes instead of smart quotes
- Duplicate list labels
- Inconsistent paragraph spacing
- Mixed numbering formats
- Inconsistent defined term formatting
- Template artifacts/placeholders
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document Types & Templates
# ---------------------------------------------------------------------------

DOC_TYPES = [
    "Commercial Lease Agreement",
    "Office Lease",
    "Retail Lease Agreement",
    "Real Estate Purchase Agreement",
    "Property Sale Agreement",
    "Deed of Trust",
    "Loan Agreement",
    "Property Management Agreement",
    "Ground Lease",
    "Sublease Agreement",
    "Assignment and Assumption Agreement",
    "Assignment of Lease",
    "Estoppel Certificate",
    "Subordination Non-Disturbance and Attornment Agreement",
    "Construction Contract",
    "Development Agreement",
    "Joint Venture Agreement",
    "Limited Partnership Agreement",
    "Operating Agreement",
    "Easement Agreement",
]

PARTY_NAMES = [
    ("Acme Properties LLC", "Bright Star Investments Inc."),
    ("Columbia Realty Group", "Delta Ventures LLC"),
    ("Eagle Point Holdings", "Fox Creek Capital"),
    ("Global Asset Partners", "Heritage Commercial LLC"),
    ("Iron Gate Development Corp.", "Jade Tower Properties"),
    ("Keystone Real Estate LLC", "Lakewood Partners Inc."),
    ("Meridian Land Corp.", "Northwind Investments"),
    ("Oakwood Commercial Group", "Pinnacle Realty Trust"),
    ("Quartz Capital LLC", "Redwood Property Management"),
    ("Summit Holdings Inc.", "Trident Real Estate Group"),
]

ADDRESSES = [
    "100 Main Street, Suite 200, New York, NY 10001",
    "500 Market Street, 15th Floor, San Francisco, CA 94105",
    "1200 Brickell Avenue, Miami, FL 33131",
    "2500 Windy Hill Road, Atlanta, GA 30339",
    "800 Congress Avenue, Austin, TX 78701",
    "350 North Wabash Avenue, Chicago, IL 60611",
    "1500 K Street NW, Washington, DC 20005",
    "700 Flower Street, Los Angeles, CA 90017",
    "One Liberty Place, Philadelphia, PA 19103",
    "200 Clarendon Street, Boston, MA 02116",
]

# Standard sections for a CRE document
SECTIONS = {
    "lease": [
        ("ARTICLE I", "DEFINITIONS"),
        ("ARTICLE II", "PREMISES AND TERM"),
        ("ARTICLE III", "RENT"),
        ("ARTICLE IV", "USE AND OCCUPANCY"),
        ("ARTICLE V", "MAINTENANCE AND REPAIRS"),
        ("ARTICLE VI", "INSURANCE"),
        ("ARTICLE VII", "INDEMNIFICATION"),
        ("ARTICLE VIII", "DEFAULT AND REMEDIES"),
        ("ARTICLE IX", "ASSIGNMENT AND SUBLETTING"),
        ("ARTICLE X", "MISCELLANEOUS"),
    ],
    "purchase": [
        ("ARTICLE I", "DEFINITIONS"),
        ("ARTICLE II", "PURCHASE AND SALE"),
        ("ARTICLE III", "PURCHASE PRICE AND PAYMENT"),
        ("ARTICLE IV", "DUE DILIGENCE"),
        ("ARTICLE V", "TITLE AND SURVEY"),
        ("ARTICLE VI", "REPRESENTATIONS AND WARRANTIES"),
        ("ARTICLE VII", "CONDITIONS TO CLOSING"),
        ("ARTICLE VIII", "CLOSING"),
        ("ARTICLE IX", "DEFAULT"),
        ("ARTICLE X", "MISCELLANEOUS PROVISIONS"),
    ],
    "loan": [
        ("ARTICLE I", "DEFINITIONS"),
        ("ARTICLE II", "THE LOAN"),
        ("ARTICLE III", "INTEREST AND PAYMENTS"),
        ("ARTICLE IV", "REPRESENTATIONS AND WARRANTIES"),
        ("ARTICLE V", "COVENANTS"),
        ("ARTICLE VI", "EVENTS OF DEFAULT"),
        ("ARTICLE VII", "REMEDIES"),
        ("ARTICLE VIII", "SECURITY"),
        ("ARTICLE IX", "INDEMNIFICATION"),
        ("ARTICLE X", "GENERAL PROVISIONS"),
    ],
    "generic": [
        ("ARTICLE I", "DEFINITIONS"),
        ("ARTICLE II", "SCOPE OF AGREEMENT"),
        ("ARTICLE III", "TERM"),
        ("ARTICLE IV", "COMPENSATION"),
        ("ARTICLE V", "OBLIGATIONS OF THE PARTIES"),
        ("ARTICLE VI", "REPRESENTATIONS AND WARRANTIES"),
        ("ARTICLE VII", "INDEMNIFICATION"),
        ("ARTICLE VIII", "TERMINATION"),
        ("ARTICLE IX", "DISPUTE RESOLUTION"),
        ("ARTICLE X", "MISCELLANEOUS"),
    ],
}

DEFINITIONS = [
    ("Affiliate", 'means any Person that directly or indirectly controls, is controlled by, or is under common control with, another Person.'),
    ("Base Rent", 'means the annual base rent payable by Tenant to Landlord as set forth in Section 3.1 hereof.'),
    ("Business Day", 'means any day other than a Saturday, Sunday, or a day on which banks in the State are authorized or required to be closed.'),
    ("Commencement Date", 'shall mean the date on which the Term of this Agreement commences as set forth in Article II.'),
    ("Default", 'means any event or condition that constitutes, or that with the passage of time or the giving of notice or both would constitute, an Event of Default.'),
    ("Effective Date", 'means the date first written above.'),
    ("Force Majeure", "means any event beyond the reasonable control of the affected party, including but not limited to acts of God, fire, flood, earthquake, epidemic, war, terrorism, strike, or governmental action."),
    ("Governmental Authority", 'means any federal, state, local, or foreign government or any court, administrative agency, or other governmental authority or instrumentality.'),
    ("Hazardous Materials", "shall mean any substance, material, or waste that is regulated by any Governmental Authority, including petroleum products, asbestos, and polychlorinated biphenyls."),
    ("Improvements", "means all buildings, structures, fixtures, and other improvements now or hereafter located on the Property."),
    ("Lease Term", 'means the period commencing on the Commencement Date and expiring on the Expiration Date, unless earlier terminated pursuant to this Agreement.'),
    ("Material Adverse Effect", "means any change, event, or condition that, individually or in the aggregate, has had or could reasonably be expected to have a material adverse effect on the Property or the business of any party hereto."),
    ("Permitted Exceptions", 'means those exceptions to title set forth on Exhibit B attached hereto.'),
    ("Person", "means any individual, corporation, partnership, limited liability company, trust, or other entity."),
    ("Property", "means the real property described on Exhibit A attached hereto, together with all Improvements thereon."),
]

# Body paragraph text snippets
BODY_PARAGRAPHS = [
    "The Landlord hereby leases to the Tenant, and the Tenant hereby leases from the Landlord, the Premises described herein for the Term and upon the conditions set forth in this Agreement.",
    "Tenant shall pay to Landlord, without notice, demand, deduction, or setoff, the Base Rent in equal monthly installments in advance on the first day of each calendar month during the Term.",
    "The obligations of each party under this Agreement shall be subject to the satisfaction or waiver of the conditions precedent set forth in this Article on or before the Closing Date.",
    "Each party represents and warrants to the other party that (a) it is duly organized, validly existing, and in good standing under the laws of its jurisdiction of organization; (b) it has full power and authority to execute and deliver this Agreement and to perform its obligations hereunder; and (c) this Agreement has been duly authorized, executed, and delivered by such party and constitutes a legal, valid, and binding obligation of such party.",
    "In no event shall either party be liable to the other party for any indirect, incidental, consequential, special, or exemplary damages arising out of or related to this Agreement, regardless of whether such damages are based on contract, tort, strict liability, or any other theory.",
    "This Agreement may not be amended, modified, or supplemented except by a written instrument executed by both parties. No waiver of any provision of this Agreement shall be effective unless in writing and signed by the party against whom enforcement is sought.",
    "All notices, requests, demands, and other communications required or permitted under this Agreement shall be in writing and shall be deemed to have been duly given when delivered personally, sent by certified mail (return receipt requested), or sent by nationally recognized overnight courier.",
    "This Agreement shall be governed by and construed in accordance with the laws of the State, without giving effect to any choice of law or conflict of law rules or provisions that would cause the application of the laws of any other jurisdiction.",
    "If any provision of this Agreement is held to be invalid, illegal, or unenforceable, the validity, legality, and enforceability of the remaining provisions shall not in any way be affected or impaired thereby.",
    "This Agreement, together with all exhibits and schedules attached hereto, constitutes the entire agreement between the parties with respect to the subject matter hereof and supersedes all prior agreements, understandings, negotiations, and discussions, whether oral or written.",
    'Tenant shall maintain the Premises in good order, condition, and repair throughout the Term, ordinary wear and tear excepted, and shall comply with all applicable laws, ordinances, rules, and regulations of all Governmental Authorities having jurisdiction.',
    "Landlord shall have the right to enter the Premises at reasonable times upon reasonable prior notice for the purpose of inspecting the same, making repairs or alterations, and showing the Premises to prospective tenants or purchasers.",
    "Upon the expiration or earlier termination of this Agreement, Tenant shall surrender the Premises to Landlord in the same condition as received, ordinary wear and tear excepted, and shall remove all of Tenant's personal property therefrom.",
    "The provisions of this Article shall survive the expiration or earlier termination of this Agreement and shall remain in full force and effect until all obligations hereunder have been satisfied in full.",
    "Neither party shall assign this Agreement or any of its rights or obligations hereunder without the prior written consent of the other party, which consent shall not be unreasonably withheld, conditioned, or delayed.",
]

# Sub-section items for lists
LIST_ITEMS = [
    "payment of all Base Rent and Additional Rent when due",
    "maintenance of insurance as required by Article VI",
    "compliance with all applicable laws and regulations",
    "preservation of the Premises in good condition",
    "timely delivery of all required notices",
    "provision of annual financial statements",
    "maintenance of adequate reserves",
    "cooperation with inspections and audits",
    "payment of all taxes and assessments",
    "compliance with environmental requirements",
]


# ---------------------------------------------------------------------------
# Formatting Bug Injection
# ---------------------------------------------------------------------------

class FormattingBug:
    """A formatting inconsistency to inject into the document."""

    def __init__(self, name: str, category: str, apply_fn: Any):
        self.name = name
        self.category = category  # Maps to checklist category A-K
        self.apply_fn = apply_fn


def _bug_mixed_heading_fonts(doc: Document, rng: random.Random) -> list[str]:
    """Inject mixed fonts in headings (category A)."""
    bugs = []
    fonts = ["Times New Roman", "Arial", "Calibri", "Cambria"]
    for para in doc.paragraphs:
        if para.style.name.startswith("Heading"):
            if rng.random() < 0.3:
                alt_font = rng.choice(fonts)
                for run in para.runs:
                    run.font.name = alt_font
                bugs.append(f"Changed heading font to {alt_font}: {para.text[:40]}")
    return bugs


def _bug_inconsistent_heading_bold(doc: Document, rng: random.Random) -> list[str]:
    """Remove bold from some headings (category A)."""
    bugs = []
    for para in doc.paragraphs:
        if para.style.name.startswith("Heading") and rng.random() < 0.25:
            for run in para.runs:
                run.font.bold = False
            bugs.append(f"Removed bold from heading: {para.text[:40]}")
    return bugs


def _bug_straight_quotes(doc: Document, rng: random.Random) -> list[str]:
    """Replace smart quotes with straight quotes in some paragraphs (category C)."""
    bugs = []
    for para in doc.paragraphs:
        if rng.random() < 0.4:
            for run in para.runs:
                if "\u201c" in run.text or "\u201d" in run.text:
                    run.text = run.text.replace("\u201c", '"').replace("\u201d", '"')
                    bugs.append(f"Straight quotes injected: {para.text[:40]}")
                    break
                if "\u2018" in run.text or "\u2019" in run.text:
                    run.text = run.text.replace("\u2018", "'").replace("\u2019", "'")
                    bugs.append(f"Straight apostrophes injected: {para.text[:40]}")
                    break
    return bugs


def _bug_inconsistent_spacing(doc: Document, rng: random.Random) -> list[str]:
    """Vary paragraph spacing inconsistently (category B)."""
    bugs = []
    for para in doc.paragraphs:
        if para.style.name == "Normal" and rng.random() < 0.3:
            pf = para.paragraph_format
            variation = rng.choice([
                (Pt(6), Pt(0)),
                (Pt(0), Pt(12)),
                (Pt(12), Pt(6)),
                (Pt(3), Pt(3)),
            ])
            pf.space_before = variation[0]
            pf.space_after = variation[1]
            bugs.append(f"Inconsistent spacing: before={variation[0]}, after={variation[1]}")
    return bugs


def _bug_mixed_body_fonts(doc: Document, rng: random.Random) -> list[str]:
    """Mix body text fonts (category B)."""
    bugs = []
    alt_fonts = ["Arial", "Calibri", "Verdana"]
    for para in doc.paragraphs:
        if para.style.name == "Normal" and rng.random() < 0.2:
            font = rng.choice(alt_fonts)
            for run in para.runs:
                run.font.name = font
            bugs.append(f"Mixed body font to {font}: {para.text[:30]}")
    return bugs


def _bug_inconsistent_alignment(doc: Document, rng: random.Random) -> list[str]:
    """Mix alignment in body paragraphs (category B)."""
    bugs = []
    for para in doc.paragraphs:
        if para.style.name == "Normal" and rng.random() < 0.15:
            para.alignment = rng.choice([
                WD_ALIGN_PARAGRAPH.LEFT,
                WD_ALIGN_PARAGRAPH.CENTER,
            ])
            bugs.append(f"Changed alignment: {para.text[:30]}")
    return bugs


def _bug_duplicate_list_labels(doc: Document, rng: random.Random) -> list[str]:
    """This is hard to inject after the fact — we inject during generation instead."""
    return []


def _bug_mixed_font_sizes(doc: Document, rng: random.Random) -> list[str]:
    """Mix font sizes in body text (category B)."""
    bugs = []
    sizes = [Pt(10), Pt(11), Pt(12), Pt(10.5)]
    for para in doc.paragraphs:
        if para.style.name == "Normal" and rng.random() < 0.15:
            size = rng.choice(sizes)
            for run in para.runs:
                run.font.size = size
            bugs.append(f"Changed font size to {size}: {para.text[:30]}")
    return bugs


def _bug_template_placeholders(doc: Document, rng: random.Random) -> list[str]:
    """Add template artifact text (category J)."""
    bugs = []
    placeholders = ["[INSERT NAME]", "[TBD]", "________", "[TO BE DETERMINED]"]
    for para in doc.paragraphs:
        if para.style.name == "Normal" and rng.random() < 0.05:
            for run in para.runs:
                run.text = run.text + " " + rng.choice(placeholders)
                bugs.append(f"Placeholder injected: {para.text[:40]}")
                break
    return bugs


def _bug_double_dashes(doc: Document, rng: random.Random) -> list[str]:
    """Replace em dashes with double hyphens (category C)."""
    bugs = []
    for para in doc.paragraphs:
        for run in para.runs:
            if "\u2014" in run.text and rng.random() < 0.5:
                run.text = run.text.replace("\u2014", "--")
                bugs.append(f"Double-dash injected: {para.text[:40]}")
    return bugs


ALL_BUGS = [
    FormattingBug("mixed_heading_fonts", "A", _bug_mixed_heading_fonts),
    FormattingBug("inconsistent_heading_bold", "A", _bug_inconsistent_heading_bold),
    FormattingBug("straight_quotes", "C", _bug_straight_quotes),
    FormattingBug("inconsistent_spacing", "B", _bug_inconsistent_spacing),
    FormattingBug("mixed_body_fonts", "B", _bug_mixed_body_fonts),
    FormattingBug("inconsistent_alignment", "B", _bug_inconsistent_alignment),
    FormattingBug("mixed_font_sizes", "B", _bug_mixed_font_sizes),
    FormattingBug("template_placeholders", "J", _bug_template_placeholders),
    FormattingBug("double_dashes", "C", _bug_double_dashes),
]


# ---------------------------------------------------------------------------
# Document Generator
# ---------------------------------------------------------------------------


def generate_synthetic_document(
    doc_number: int,
    output_dir: Path,
    seed: int | None = None,
    bug_density: float = 0.7,
) -> tuple[Path, list[str]]:
    """Generate a synthetic CRE legal document with formatting bugs.

    Args:
        doc_number: Document number (1-indexed).
        output_dir: Directory to save the document.
        seed: Random seed for reproducibility.
        bug_density: Fraction of available bugs to inject (0.0-1.0).

    Returns:
        Tuple of (docx_path, list of injected bug descriptions).
    """
    rng = random.Random(seed if seed is not None else doc_number * 42 + 7)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pick doc type and parties
    doc_type_name = DOC_TYPES[doc_number % len(DOC_TYPES)]
    party1, party2 = PARTY_NAMES[doc_number % len(PARTY_NAMES)]
    address = ADDRESSES[doc_number % len(ADDRESSES)]

    # Pick section template
    if "lease" in doc_type_name.lower() or "sublease" in doc_type_name.lower():
        section_template = "lease"
    elif "purchase" in doc_type_name.lower() or "sale" in doc_type_name.lower():
        section_template = "purchase"
    elif "loan" in doc_type_name.lower() or "deed" in doc_type_name.lower():
        section_template = "loan"
    else:
        section_template = "generic"

    sections = SECTIONS[section_template]

    # Create document
    doc = Document()

    # --- Title ---
    title_para = doc.add_heading(doc_type_name.upper(), level=0)
    for run in title_para.runs:
        run.font.name = "Times New Roman"
        run.font.size = Pt(16)
        run.font.bold = True

    # --- Preamble ---
    preamble = doc.add_paragraph()
    preamble.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = preamble.add_run(
        f"THIS {doc_type_name.upper()} (this \u201cAgreement\u201d) is entered into as of "
        f"the _____ day of ____________, 2024 (the \u201cEffective Date\u201d), by and between "
        f"{party1} (\u201cParty A\u201d) and {party2} (\u201cParty B\u201d)."
    )
    run.font.name = "Times New Roman"
    run.font.size = Pt(12)

    # --- Recitals ---
    recitals_heading = doc.add_heading("RECITALS", level=1)
    for run in recitals_heading.runs:
        run.font.name = "Times New Roman"
        run.font.size = Pt(14)
        run.font.bold = True

    recitals = [
        f"WHEREAS, Party A owns certain real property located at {address} (the \u201cProperty\u201d); and",
        f"WHEREAS, Party B desires to {_get_verb_for_type(doc_type_name)} the Property upon the terms and conditions set forth herein; and",
        "WHEREAS, the parties desire to set forth their agreement with respect to the foregoing;",
    ]
    for rec_text in recitals:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        r = p.add_run(rec_text)
        r.font.name = "Times New Roman"
        r.font.size = Pt(12)

    now_para = doc.add_paragraph()
    now_para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = now_para.add_run(
        "NOW, THEREFORE, in consideration of the mutual covenants and agreements herein "
        "contained, and for other good and valuable consideration, the receipt and sufficiency "
        "of which are hereby acknowledged, the parties agree as follows:"
    )
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)

    # --- Articles / Sections ---
    for art_num, (article_label, article_title) in enumerate(sections, 1):
        # Article heading
        heading = doc.add_heading(f"{article_label}\n{article_title}", level=1)
        for run in heading.runs:
            run.font.name = "Times New Roman"
            run.font.size = Pt(14)
            run.font.bold = True
            run.font.underline = True

        # Definitions article gets special treatment
        if "DEFINITION" in article_title:
            selected_defs = rng.sample(DEFINITIONS, min(len(DEFINITIONS), rng.randint(8, 12)))
            selected_defs.sort(key=lambda d: d[0])
            for def_name, def_text in selected_defs:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                r1 = p.add_run(f"\u201c{def_name}\u201d ")
                r1.font.name = "Times New Roman"
                r1.font.size = Pt(12)
                r1.font.bold = True
                r2 = p.add_run(def_text)
                r2.font.name = "Times New Roman"
                r2.font.size = Pt(12)
            continue

        # Sub-sections
        num_subsections = rng.randint(2, 5)
        for sub_num in range(1, num_subsections + 1):
            # Sub-heading
            sub_heading = doc.add_heading(
                f"Section {art_num}.{sub_num}", level=2
            )
            for run in sub_heading.runs:
                run.font.name = "Times New Roman"
                run.font.size = Pt(12)
                run.font.bold = True

            # Body paragraphs
            num_paras = rng.randint(1, 3)
            for _ in range(num_paras):
                body_text = rng.choice(BODY_PARAGRAPHS)
                # Contextual substitution
                body_text = body_text.replace("Landlord", "Party A").replace("Tenant", "Party B")
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                r = p.add_run(body_text)
                r.font.name = "Times New Roman"
                r.font.size = Pt(12)

            # Sometimes add a list
            if rng.random() < 0.4:
                list_count = rng.randint(3, 6)
                labels = _get_list_labels(list_count, rng, inject_dup=rng.random() < 0.3)
                selected_items = rng.sample(LIST_ITEMS, min(len(LIST_ITEMS), list_count))
                for label, item in zip(labels, selected_items):
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Inches(0.5)
                    r = p.add_run(f"{label} {item};")
                    r.font.name = "Times New Roman"
                    r.font.size = Pt(12)

    # --- Signature Block ---
    sig_heading = doc.add_heading("IN WITNESS WHEREOF", level=1)
    for run in sig_heading.runs:
        run.font.name = "Times New Roman"
        run.font.bold = True

    sig_intro = doc.add_paragraph()
    r = sig_intro.add_run(
        "IN WITNESS WHEREOF, the parties hereto have executed this Agreement "
        "as of the date first written above."
    )
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)

    for party_name in [party1, party2]:
        doc.add_paragraph()  # Spacer
        p = doc.add_paragraph()
        r = p.add_run(party_name.upper())
        r.font.name = "Times New Roman"
        r.font.size = Pt(12)
        r.font.bold = True

        for field in ["By:", "Name:", "Title:", "Date:"]:
            p = doc.add_paragraph()
            r = p.add_run(f"{field} ____________________________")
            r.font.name = "Times New Roman"
            r.font.size = Pt(12)

    # --- Exhibit A (Property Description) ---
    doc.add_page_break()
    exhibit_heading = doc.add_heading("EXHIBIT A", level=1)
    for run in exhibit_heading.runs:
        run.font.name = "Times New Roman"
        run.font.bold = True
        run.font.underline = True

    sub = doc.add_heading("Property Description", level=2)
    for run in sub.runs:
        run.font.name = "Times New Roman"

    p = doc.add_paragraph()
    r = p.add_run(f"The property located at {address}, more particularly described as follows:")
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)

    p = doc.add_paragraph()
    r = p.add_run(
        f"All that certain lot, piece, or parcel of land situated in the City of "
        f"{address.split(',')[-2].strip()}, with the buildings and improvements thereon "
        f"erected, known and designated as {address.split(',')[0]}."
    )
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)

    # --- Save the clean document first, then inject bugs ---
    # Determine which bugs to inject
    num_bugs = max(3, int(len(ALL_BUGS) * bug_density))
    selected_bugs = rng.sample(ALL_BUGS, min(num_bugs, len(ALL_BUGS)))

    all_injected = []
    for bug in selected_bugs:
        try:
            injected = bug.apply_fn(doc, rng)
            all_injected.extend(injected)
        except Exception as e:
            logger.debug(f"Bug injection failed for {bug.name}: {e}")

    # Save
    safe_name = doc_type_name.lower().replace(" ", "_")[:30]
    filename = f"synth_{doc_number:03d}_{safe_name}.docx"
    output_path = output_dir / filename
    doc.save(str(output_path))

    logger.info(f"  Generated: {filename} ({len(all_injected)} bugs injected)")
    return output_path, all_injected


def generate_batch(
    count: int,
    output_dir: Path,
    base_seed: int = 12345,
    bug_density: float = 0.7,
) -> list[tuple[Path, list[str]]]:
    """Generate a batch of synthetic documents.

    Args:
        count: Number of documents to generate.
        output_dir: Output directory.
        base_seed: Base random seed.
        bug_density: Bug injection density.

    Returns:
        List of (path, bugs) tuples.
    """
    results = []
    for i in range(1, count + 1):
        path, bugs = generate_synthetic_document(
            doc_number=i,
            output_dir=output_dir,
            seed=base_seed + i,
            bug_density=bug_density,
        )
        results.append((path, bugs))
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_verb_for_type(doc_type: str) -> str:
    """Get appropriate verb for the document type."""
    dt = doc_type.lower()
    if "lease" in dt:
        return "lease"
    if "purchase" in dt or "sale" in dt:
        return "purchase"
    if "loan" in dt or "deed" in dt:
        return "finance the acquisition of"
    if "management" in dt:
        return "manage"
    if "construction" in dt or "development" in dt:
        return "develop improvements upon"
    return "enter into this transaction concerning"


def _get_list_labels(count: int, rng: random.Random, inject_dup: bool = False) -> list[str]:
    """Generate list labels, optionally injecting a duplicate."""
    style = rng.choice(["alpha_paren", "roman_paren", "numeric_dot"])

    if style == "alpha_paren":
        labels = [f"({chr(ord('a') + i)})" for i in range(count)]
    elif style == "roman_paren":
        romans = ["(i)", "(ii)", "(iii)", "(iv)", "(v)", "(vi)", "(vii)", "(viii)"]
        labels = romans[:count]
    else:
        labels = [f"{i + 1}." for i in range(count)]

    if inject_dup and len(labels) >= 3:
        # Duplicate a label to create a bug
        dup_idx = rng.randint(1, len(labels) - 1)
        labels[dup_idx] = labels[dup_idx - 1]

    return labels
