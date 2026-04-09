import argparse
import json
import os
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from llm_client import call_llm

COLUMNS = [
    "Patient_ID",
    "Hospital_No",
    "ICD_Code",
    "Age",
    "Sex",
    "HTN",
    "DM",
    "Family_History",
    "Family_History_Details",
    "Chief_Complaint",
    "Mouth_Opening_Status",
    "Mouth_Opening_Details",
    "Soft_Tissue_Exam",
    "Specific_Findings",
    "Lesion_Type",
    "Lesion_Color",
    "Lesion_Site",
    "Burning_Sensation",
    "Pain_Details",
    "Bleeding_Present",
    "Bleeding_Details",
    "Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details",
    "Clinical_Diagnosis",
    "Final_Provisional_Dx",
    "Differential_Diagnosis",
    "TNM_Stage",
    "Histological_Subgroup",
    "Investigations",
    "Biopsy_Details",
    "Treatment_Plan",
    "Tobacco_Use",
    "Tobacco_Use_Details",
    "Areca_Nut_Use",
    "Areca_Nut_Details",
    "Alcohol_Use",
    "Alcohol_Use_Details",
    "Oral_Hygiene_Status",
    "Trauma_Irritation_History",
]

YES_NO_FIELDS = {
    "HTN",
    "DM",
    "Family_History",
    "Burning_Sensation",
    "Bleeding_Present",
    "Tobacco_Use",
    "Areca_Nut_Use",
    "Alcohol_Use",
}

MISSING_VALUES = {"", "not documented", "none", "nan", "[]", "{}"}
PATIENT_START_TEMPLATE = "<<<PATIENT_START::{patient_id}>>>"
PATIENT_END_TEMPLATE = "<<<PATIENT_END::{patient_id}>>>"

ORAL_PAGE_TERMS = [
    "oral", "buccal", "mucosa", "tongue", "palate", "gingiva", "gingivobuccal",
    "gingivo buccal", "submandibular", "mouth opening", "trismus", "lesion", "ulcer",
    "growth", "vestibule", "faucial", "retromolar", "soft palate", "hard palate",
    "neck node", "lymph node", "palpable node", "calculus", "debris", "oral hygiene",
    "burning sensation", "clinical diagnosis", "provisional diagnosis", "differential diagnosis",
    "biopsy", "histopath", "fnac", "carcinoma", "osmf", "ocsmf", "leukoplakia",
    "erythroplakia", "periodontology", "prosthodontics", "oral surgery",
]

GENERAL_PAGE_TERMS = [
    "hospital no", "registration no", "mrd no", "uhid", "op no", "age", "sex",
    "history", "medical history", "past history", "family history", "htn", "hypertension",
    "dm", "diabetes", "diabetic", "insulin", "metformin", "thyroid", "thyronorm",
    "tobacco", "smoking", "cigarette", "beedi", "bidi", "gutka", "gutkha", "khaini",
    "pan masala", "areca", "betel", "supari", "alcohol", "drinking",
]

IRRELEVANT_PAGE_TERMS = [
    "ophthalmology", "visual acuity", "fundus", "refraction", "psychiatry", "sertraline",
    "venlafaxine", "schizo", "2d echo", "cabg", "angioplasty", "stemi", "ecg", "melena",
    "hematemesis", "dialysis", "nephrology", "orthopedics",
]

FIELD_KEYWORDS = {
    "Hospital_No": ["hospital no", "registration no", "mrd no", "uhid", "op no"],
    "ICD_Code": ["icd", "icd code", "icdo", "c06", "c02", "d00"],
    "Age": ["age", "years", "yrs", "year old", "/m", "/f"],
    "Sex": ["male", "female", "/m", "/f", "sex"],
    "HTN": ["htn", "hypertension", "antihypertensive"],
    "DM": ["dm", "diabetes", "diabetic", "metformin", "insulin"],
    "Family_History": ["family history", "maternal", "paternal", "mother", "father", "brother", "sister"],
    "Family_History_Details": ["family history", "runs in family", "mother", "father", "brother", "sister"],
    "Chief_Complaint": ["chief complaint", "complaint", "c/o", "presents with"],
    "Mouth_Opening_Status": ["mouth opening", "trismus", "restricted", "reduced", "normal"],
    "Mouth_Opening_Details": ["mouth opening", "interincisal", "trismus", "restricted"],
    "Soft_Tissue_Exam": ["soft tissue", "mucosa", "vestibule", "gingiva", "palate", "tongue"],
    "Specific_Findings": ["finding", "induration", "ulcer", "growth", "tenderness", "surface", "margin"],
    "Lesion_Type": ["ulcer", "growth", "patch", "plaque", "swelling", "lesion", "mass"],
    "Lesion_Color": ["red", "white", "mixed", "erythematous", "pale", "blanched"],
    "Lesion_Site": ["buccal", "tongue", "palate", "vestibule", "retromolar", "gingiva", "commissure"],
    "Burning_Sensation": ["burning sensation", "burning"],
    "Pain_Details": ["pain", "painful", "tenderness", "odynophagia"],
    "Bleeding_Present": ["bleeding", "bleeds", "bleeding on probing"],
    "Bleeding_Details": ["bleeding", "bleeding on probing", "spontaneous bleed"],
    "Cervical_Lymphadenopathy": ["lymph node", "neck node", "submandibular node", "palpable node"],
    "Cervical_Lymphadenopathy_Details": ["lymph node", "neck node", "submandibular node", "level ii", "level iii"],
    "Clinical_Diagnosis": ["clinical diagnosis", "diagnosis", "impression"],
    "Final_Provisional_Dx": ["provisional diagnosis", "final diagnosis", "working diagnosis"],
    "Differential_Diagnosis": ["differential diagnosis", "differentials"],
    "TNM_Stage": ["tnm", "t1", "t2", "t3", "n0", "n1", "stage"],
    "Histological_Subgroup": ["well differentiated", "moderately differentiated", "poorly differentiated", "histology"],
    "Investigations": ["investigation", "ct", "mri", "pet", "biopsy", "fnac", "blood", "histopath"],
    "Biopsy_Details": ["biopsy", "histopath", "fnac", "hpe", "incisional biopsy"],
    "Treatment_Plan": ["treatment plan", "plan", "advised", "surgery", "radiotherapy", "chemotherapy"],
    "Tobacco_Use": ["tobacco", "smoking", "cigarette", "beedi", "bidi", "gutka", "gutkha", "khaini", "pan masala"],
    "Tobacco_Use_Details": ["tobacco", "smoking", "cigarette", "beedi", "bidi", "gutka", "gutkha", "khaini", "pan masala"],
    "Areca_Nut_Use": ["areca", "betel", "supari"],
    "Areca_Nut_Details": ["areca", "betel", "supari"],
    "Alcohol_Use": ["alcohol", "beer", "wine", "liquor", "drinking"],
    "Alcohol_Use_Details": ["alcohol", "beer", "wine", "liquor", "drinking"],
    "Oral_Hygiene_Status": ["oral hygiene", "calculus", "debris", "plaque", "stains"],
    "Trauma_Irritation_History": ["sharp tooth", "trauma", "irritation", "frictional", "cheek bite", "tooth irritation"],
}

GLOBAL_MEDICAL_TERMS = sorted({term for terms in FIELD_KEYWORDS.values() for term in terms})

EXTRACTION_RULES = """
You are extracting oral-case-sheet data from OCR text.

Core rules:
- Return ONLY valid JSON.
- Never mix one patient's facts into another patient's record.
- Use exact field names for the 39 fixed fields.
- Use "Not documented" when evidence is absent or too weak.
- Never invent values.
- Prefer oral/maxillofacial/pathology evidence for lesion-related fields.
- Prefer general history/demographic evidence for age, sex, comorbidities, and habits.
- If two snippets conflict, prefer the more specific snippet with clearer wording.
- Use the provided evidence packets first, then the routed text.
- Keep extra important findings in extra_findings even if they do not fit neatly into the 39 fixed fields.
- Keep evidence_map concise and field-linked.

IMPORTANT — Prefill trust:
- The CURRENT_PREFILL_JSON already has values extracted from filenames and regex patterns. Trust these values (especially Age, Sex, Hospital_No) unless the OCR text clearly contradicts them.
- For ANY field still showing "Not documented" in the prefill, you must scan ALL provided text sections very carefully before giving up. Look for abbreviations like k/c/o, H/o, c/o, S/P, HTN, DM, T2DM, OSMF, etc.
- Pay special attention to: HTN (hypertension), DM (diabetes, T2DM), Tobacco/Areca/Alcohol habits, and Family History.

Normalization rules:
- Sex -> Male / Female / Not documented.
- HTN, DM, Family_History, Burning_Sensation, Bleeding_Present, Tobacco_Use, Areca_Nut_Use, Alcohol_Use -> Yes / No / Not documented.
- Mouth_Opening_Status -> Normal / Restricted / Not documented.
- Oral_Hygiene_Status -> Good / Fair / Poor / Not documented.
- Cervical_Lymphadenopathy -> Positive / Negative / Not documented.
- Family history must come from explicit family-history text, not generic past history.
- Bleeding_Present refers to oral complaint context, not unrelated GI bleeding.
""".strip()


def is_missing(value: Any) -> bool:
    return str(value).strip().lower() in MISSING_VALUES


EXTRA_FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "title": {"type": "string"},
        "detail": {"type": "string"},
        "evidence": {"type": "string"},
        "source_hint": {"type": "string"},
    },
    "required": ["category", "title", "detail", "evidence", "source_hint"],
}

EVIDENCE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string"},
        "evidence": {"type": "string"},
        "source_hint": {"type": "string"},
    },
    "required": ["field", "evidence", "source_hint"],
}

PATIENT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "Patient_ID": {"type": "string"},
        "fields": {
            "type": "object",
            "properties": {col: {"type": "string"} for col in COLUMNS},
            "required": COLUMNS,
        },
        "patient_summary": {"type": "string"},
        "extra_findings": {
            "type": "array",
            "items": EXTRA_FINDING_SCHEMA,
        },
        "evidence_map": {
            "type": "array",
            "items": EVIDENCE_ITEM_SCHEMA,
        },
    },
    "required": ["Patient_ID", "fields", "patient_summary", "extra_findings", "evidence_map"],
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "patients": {
            "type": "array",
            "items": PATIENT_RESPONSE_SCHEMA,
        }
    },
    "required": ["patients"],
}


def normalize_spaces(text: str) -> str:
    text = text.replace("\x0c", "\n")
    lines: List[str] = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def dedupe_lines(text: str) -> str:
    seen = set()
    out: List[str] = []
    for line in text.splitlines():
        key = line.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(line.strip())
    return "\n".join(out)


# ---------------------------------------------------------------------------
#  NEW PREPROCESSING LAYER (inspired by Datalab Marker, Docling, PaddleOCR)
# ---------------------------------------------------------------------------

_BOILERPLATE_PATTERNS = [
    re.compile(r"^\s*=+\s*page_\d+\.txt\s*=+\s*$", re.I),                      # ===== page_001.txt =====
    re.compile(r"^\s*Manipal\s*-\s*576104.*$", re.I),                            # hospital address
    re.compile(r"^\s*Phone\s*:\s*0820.*$", re.I),                                # phone/fax line
    re.compile(r"^\s*Email\s*:\s*helpdesk.*$", re.I),                             # email line
    re.compile(r"^\s*MR\s*-\s*\d{3,}.*$", re.I),                                # MR form codes
    re.compile(r"^\s*Service\s+date\s*$", re.I),                                 # empty form header
    re.compile(r"^\s*History,?\s*Examination,?\s*Treatment.*$", re.I),            # template header
    re.compile(r"^\s*Inv\.?\s*Ordered\s*$", re.I),                               # template header
    re.compile(r"^\s*P\.?T\.?O\.?\s*$", re.I),                                   # PTO marker
    re.compile(r"^\s*\*\s*(Continue|In case|Avail|Please|3rd Saturday|Always).*$", re.I),  # pharmacy footer boilerplate
    re.compile(r".*ಆಹಾರ.*$"),                                                    # Kannada food instruction boilerplate
]

_EMPTY_VITALS_RE = re.compile(
    r"^\s*Ht\.?\s*:?\s*_+.*Wt\.?\s*:?\s*_+.*Kg.*BP\s*:?\s*_+.*mmHg.*Pulse\s*:?\s*_+.*$",
    re.I,
)
_FILLED_VITALS_RE = re.compile(
    r"\b(?:BP|Pulse|SpO2|Temp|HR|RR)\s*:?\s*\d",
    re.I,
)


def extract_filename_metadata(filenames: List[str]) -> Dict[str, str]:
    """Extract Hospital_No, Age, Sex from structured filenames.
    Pattern: NNN_Category_HospitalNo_Age_Sex_...
    Example: 004_Agriculture_03289327_53_M_532_20250612_141623.txt
                              ^^^^^^^^  ^^  ^
                              HospNo   Age Sex
    """
    for fname in filenames:
        m = re.match(r"\d+_\w+_(\d{5,})_(\d{1,3})_([MF])_", fname)
        if m:
            age = int(m.group(2))
            return {
                "Hospital_No": m.group(1),
                "Age": str(age) if 1 <= age <= 120 else "Not documented",
                "Sex": "Male" if m.group(3) == "M" else "Female",
            }
    return {}


def strip_boilerplate(text: str) -> str:
    """Remove hospital headers, footers, empty form templates, and OCR page markers.
    Preserves lines that contain actual clinical data even if they partially match."""
    out: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Skip pure boilerplate
        if any(pat.match(stripped) for pat in _BOILERPLATE_PATTERNS):
            continue

        # Skip empty vitals template (Ht.: _______ Wt.: _______)
        # but keep lines where vitals are actually filled in
        if _EMPTY_VITALS_RE.match(stripped) and not _FILLED_VITALS_RE.search(stripped):
            continue

        out.append(stripped)
    return "\n".join(out)


def is_noise_page(text: str) -> bool:
    """Detect OCR garbage pages: repeated numbers, identical values, or near-empty content.
    Inspired by Datalab Marker's page quality scoring."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        # Very short pages are NOT noise — they might be a one-liner with a diagnosis
        return False

    # Check for pages that are mostly just numbers (like 1,2,3,...287)
    numeric_lines = sum(1 for l in lines if re.match(r"^[\d\s.,|\-]+$", l))
    if len(lines) >= 5 and numeric_lines / len(lines) > 0.70:
        return True

    # Check for pages where >70% of lines are the same value (like 10000 x 170)
    if len(lines) >= 10:
        from collections import Counter
        counts = Counter(l.lower() for l in lines)
        most_common_count = counts.most_common(1)[0][1]
        if most_common_count / len(lines) > 0.70:
            return True

    # Check for pages with very few distinct words (OCR artifacts)
    all_words = set(re.findall(r"[a-zA-Z]{2,}", text.lower()))
    if len(lines) >= 10 and len(all_words) < 3:
        return True

    return False


def score_page_quality(text: str) -> float:
    """Score a page 0.0-1.0 based on information density.
    High scores = rich clinical content. Low scores = templates/noise.
    Inspired by PaddleOCR's layout classification."""
    words = re.findall(r"[a-zA-Z]{2,}", text.lower())
    if not words:
        return 0.0

    total_words = len(words)
    unique_words = len(set(words))

    # Medical term density: how many known clinical terms appear
    med_hits = sum(1 for term in GLOBAL_MEDICAL_TERMS if term in text.lower())

    # Section header bonus: presence of clinical section headers
    section_headers = [
        "chief complaint", "presenting complaint", "diagnosis", "provisional diagnosis",
        "treatment plan", "investigations", "biopsy", "medical history", "past history",
        "family history", "oral abusive habits", "soft tissue", "mouth opening",
        "clinical diagnosis", "impression", "o/e", "examination",
    ]
    header_bonus = sum(0.15 for h in section_headers if h in text.lower())

    # Penalize very short pages (but don't zero them — a short diagnosis is still valuable)
    length_factor = min(1.0, len(text) / 200)

    # Uniqueness ratio: penalizes repetitive garbage
    uniqueness = unique_words / total_words if total_words > 0 else 0.0

    score = (
        0.35 * min(1.0, med_hits / 5)
        + 0.25 * uniqueness
        + 0.20 * length_factor
        + 0.20 * min(1.0, header_bonus)
    )
    return round(min(1.0, score), 3)


def read_files(folder_path: str) -> List[Tuple[str, str]]:
    """Read OCR text files with full preprocessing pipeline:
    1. Strip internal page markers (===== page_XXX.txt =====)
    2. Strip boilerplate (hospital headers, template lines)
    3. Detect and drop noise pages
    4. Score remaining pages by quality
    5. Return sorted by quality (highest first)
    """
    files = sorted(f for f in os.listdir(folder_path) if f.endswith(".txt"))
    result: List[Tuple[str, str, float]] = []  # (fname, cleaned_text, quality_score)
    noise_dropped = 0

    for fname in files:
        path = os.path.join(folder_path, fname)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()

        # Step 1: Normalize whitespace
        text = normalize_spaces(raw)

        # Step 2: Strip boilerplate (headers, footers, empty templates)
        text = strip_boilerplate(text)

        # Step 3: Deduplicate lines within this file
        text = dedupe_lines(text)

        # Step 4: Skip if nothing useful remains
        if not text.strip() or len(text.strip()) < 10:
            noise_dropped += 1
            continue

        # Step 5: Detect noise pages
        if is_noise_page(text):
            noise_dropped += 1
            continue

        # Step 6: Score page quality
        quality = score_page_quality(text)
        result.append((fname, text, quality))

    # Sort by quality score descending — best pages first
    result.sort(key=lambda x: x[2], reverse=True)

    if noise_dropped > 0:
        print("  [preprocess] Dropped {n} noise/empty page(s)".format(n=noise_dropped))

    # Return without the score (rest of pipeline expects (fname, txt) tuples)
    return [(fname, txt) for fname, txt, _ in result]


def count_matches(low: str, terms: Sequence[str]) -> int:
    return sum(1 for term in terms if term in low)


def route_pages(file_contents: List[Tuple[str, str]]) -> Dict[str, List[Tuple[str, str]]]:
    oral_pages: List[Tuple[str, str]] = []
    general_pages: List[Tuple[str, str]] = []
    dropped_pages: List[Tuple[str, str]] = []
    scored_rows: List[Tuple[str, str, int, int, int]] = []

    for fname, txt in file_contents:
        low = txt.lower()
        oral_score = count_matches(low, ORAL_PAGE_TERMS)
        general_score = count_matches(low, GENERAL_PAGE_TERMS)
        irrelevant_score = count_matches(low, IRRELEVANT_PAGE_TERMS)
        scored_rows.append((fname, txt, oral_score, general_score, irrelevant_score))

        if oral_score >= 2:
            oral_pages.append((fname, txt))
            if general_score >= 1:
                general_pages.append((fname, txt))
            continue

        if general_score >= 2 and irrelevant_score <= 1:
            general_pages.append((fname, txt))
            continue

        if irrelevant_score >= 2 and oral_score == 0 and general_score == 0:
            dropped_pages.append((fname, txt))
            continue

        if oral_score >= 1:
            oral_pages.append((fname, txt))
        elif general_score >= 1:
            general_pages.append((fname, txt))
        else:
            dropped_pages.append((fname, txt))

    if not oral_pages and scored_rows:
        ranked = sorted(scored_rows, key=lambda x: (x[2], x[3], -x[4], len(x[1])), reverse=True)
        oral_pages = [(fname, txt) for fname, txt, _, _, _ in ranked[: min(2, len(ranked))]]

    if not general_pages and scored_rows:
        ranked = sorted(scored_rows, key=lambda x: (x[3], x[2], -x[4], len(x[1])), reverse=True)
        general_pages = [(fname, txt) for fname, txt, _, _, _ in ranked[: min(2, len(ranked))]]

    return {"oral": oral_pages, "general": general_pages, "dropped": dropped_pages}


def controlled_truncate(text: str, max_chars: int) -> Tuple[str, bool]:
    text = text.strip()
    if len(text) <= max_chars:
        return text, False
    head = int(max_chars * 0.70)
    tail = max_chars - head
    clipped = text[:head] + "\n\n...[TRUNCATED MIDDLE FOR TOKEN CONTROL]...\n\n" + text[-tail:]
    return clipped, True


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def split_into_snippets(file_contents: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    snippets: List[Dict[str, Any]] = []
    seen = set()
    for fname, txt in file_contents:
        for raw_line in txt.splitlines():
            line = raw_line.strip(" -•:\t")
            if len(line) < 6:
                continue
            chunks = re.split(r"(?<=[.;])\s+|\s{2,}", line)
            for chunk in chunks:
                chunk = chunk.strip(" -•:\t")
                if len(chunk) < 6:
                    continue
                key = chunk.lower()
                if key in seen:
                    continue
                seen.add(key)
                tokens = set(tokenize(chunk))
                snippets.append(
                    {
                        "text": chunk,
                        "source": fname,
                        "tokens": tokens,
                        "low": key,
                    }
                )
    return snippets


def lexical_similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ta = a["tokens"]
    tb = b["tokens"]
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    if inter == 0:
        return 0.0
    union = len(ta | tb)
    shared_med = sum(1 for term in GLOBAL_MEDICAL_TERMS if term in a["low"] and term in b["low"])
    same_source_bonus = 0.08 if a["source"] == b["source"] else 0.0
    return (inter / union) + 0.06 * shared_med + same_source_bonus


def build_clusters(snippets: List[Dict[str, Any]], max_clusters: int = 14) -> List[Dict[str, Any]]:
    if not snippets:
        return []

    clusters: List[Dict[str, Any]] = []
    ranked_snippets = sorted(
        snippets,
        key=lambda s: (sum(1 for term in GLOBAL_MEDICAL_TERMS if term in s["low"]), len(s["text"])),
        reverse=True,
    )

    for snip in ranked_snippets:
        best_idx: Optional[int] = None
        best_score = 0.0
        for idx, cluster in enumerate(clusters):
            score = lexical_similarity(snip, cluster["centroid"])
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx is not None and best_score >= 0.24:
            clusters[best_idx]["items"].append(snip)
            if len(snip["tokens"]) > len(clusters[best_idx]["centroid"]["tokens"]):
                clusters[best_idx]["centroid"] = snip
        elif len(clusters) < max_clusters:
            clusters.append({"centroid": snip, "items": [snip]})
        else:
            smallest = min(range(len(clusters)), key=lambda i: len(clusters[i]["items"]))
            clusters[smallest]["items"].append(snip)

    packed: List[Dict[str, Any]] = []
    for cluster in clusters:
        items = cluster["items"]
        items_sorted = sorted(items, key=lambda x: len(x["text"]), reverse=True)
        packed.append(
            {
                "label": cluster_label(items_sorted),
                "summary": " | ".join(item["text"] for item in items_sorted[:3]),
                "source_hint": ", ".join(sorted({item["source"] for item in items_sorted[:3]})),
                "items": items_sorted,
            }
        )
    packed.sort(key=lambda c: len(c["items"]), reverse=True)
    return packed


def cluster_label(items: List[Dict[str, Any]]) -> str:
    bag: Dict[str, int] = defaultdict(int)
    for item in items[:4]:
        for term in GLOBAL_MEDICAL_TERMS:
            if term in item["low"]:
                bag[term] += 1
    if not bag:
        return "general evidence"
    return ", ".join([term for term, _ in sorted(bag.items(), key=lambda kv: (-kv[1], kv[0]))[:3]])


def rank_snippets_for_field(
    field: str,
    snippets: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    max_items: int = 4,
) -> List[Dict[str, Any]]:
    keywords = FIELD_KEYWORDS.get(field, [])
    scored: List[Tuple[float, Dict[str, Any]]] = []

    for snip in snippets:
        low = snip["low"]
        direct_hits = sum(2 for kw in keywords if kw in low)
        med_hits = sum(1 for term in GLOBAL_MEDICAL_TERMS if term in low)
        numeric_bonus = 1 if re.search(r"\b\d+(?:mm|cm|x\d|/m|/f|yrs|year)\b", low) else 0
        negative_context_penalty = 2 if any(term in low for term in IRRELEVANT_PAGE_TERMS) else 0
        score = direct_hits + 0.25 * med_hits + 0.8 * numeric_bonus - negative_context_penalty
        if score > 0:
            scored.append((score, snip))

    scored.sort(key=lambda x: (x[0], len(x[1]["text"])), reverse=True)
    picked = [snip for _, snip in scored[:max_items]]

    if clusters:
        boosted: List[Dict[str, Any]] = []
        for cluster in clusters:
            cluster_text = (cluster["label"] + " " + cluster["summary"]).lower()
            cluster_score = sum(1 for kw in keywords if kw in cluster_text)
            if cluster_score >= 2:
                boosted.extend(cluster["items"][:2])
        for item in boosted:
            if item not in picked:
                picked.append(item)
            if len(picked) >= max_items:
                break

    return picked[:max_items]


def extract_age_sex(text: str) -> Tuple[str, str]:
    m = re.search(r"\b(\d{1,3})\s*[/,\- ]\s*(male|female|m|f)\b", text, re.I)
    if m:
        age = int(m.group(1))
        sex = m.group(2).strip().lower()
        return (str(age) if 1 <= age <= 120 else "Not documented",
                "Male" if sex in ("m", "male") else "Female")

    age = "Not documented"
    sex = "Not documented"

    m_age = re.search(r"\bage[:\s\-]*(\d{1,3})\b", text, re.I)
    if m_age:
        n = int(m_age.group(1))
        if 1 <= n <= 120:
            age = str(n)

    m_sex = re.search(r"\bsex[:\s\-]*(male|female|m|f)\b", text, re.I)
    if m_sex:
        s = m_sex.group(1).strip().lower()
        sex = "Male" if s in ("m", "male") else "Female"

    return age, sex


def detect_binary(low: str, positive_patterns: Sequence[str], negative_patterns: Sequence[str]) -> str:
    for pat in negative_patterns:
        if re.search(pat, low):
            return "No"
    for pat in positive_patterns:
        if re.search(pat, low):
            return "Yes"
    return "Not documented"


def cheap_prefill(patient_id: str, oral_text: str, general_text: str, filename_meta: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    row = {col: "Not documented" for col in COLUMNS}
    row["Patient_ID"] = patient_id

    combined = (general_text + "\n\n" + oral_text).strip()
    combined_low = combined.lower()
    oral_low = oral_text.lower()
    general_low = general_text.lower()

    m = re.search(r"(?:hospital\s*no|registration\s*no|mrd\s*no|uhid|op\s*no)[:\s\-]*([a-z0-9/\-]{4,})", combined, re.I)
    if m:
        row["Hospital_No"] = m.group(1).strip()

    age, sex = extract_age_sex(combined)
    row["Age"] = age
    row["Sex"] = sex

    # Filename metadata: OVERRIDE text-based extraction (filenames are more reliable than OCR regex)
    if filename_meta:
        meta_used: List[str] = []
        if filename_meta.get("Hospital_No"):
            if row["Hospital_No"] == "Not documented" or row["Hospital_No"] != filename_meta["Hospital_No"]:
                row["Hospital_No"] = filename_meta["Hospital_No"]
                meta_used.append("Hospital_No")
        if filename_meta.get("Age"):
            fn_age = int(filename_meta["Age"])
            text_age = int(row["Age"]) if row["Age"].isdigit() else None
            # Filename wins if: text missed it, or text found a suspicious value (too far from filename)
            if text_age is None or abs(text_age - fn_age) > 10:
                row["Age"] = filename_meta["Age"]
                meta_used.append("Age")
        if filename_meta.get("Sex"):
            if row["Sex"] == "Not documented":
                row["Sex"] = filename_meta["Sex"]
                meta_used.append("Sex")
        if meta_used:
            print("  [preprocess] Filled from filename: {fields}".format(fields=", ".join(meta_used)))

    row["HTN"] = detect_binary(general_low, [r"\bhtn\b", r"\bhypertension\b", r"\bantihypertensive\b"], [r"\bno\b.{0,20}\b(htn|hypertension)\b"])
    row["DM"] = detect_binary(general_low, [r"\bdm\b", r"\bdiabetes\b", r"\bdiabetic\b", r"\bmetformin\b", r"\binsulin\b"], [r"\bno\b.{0,20}\b(dm|diabetes|diabetic)\b"])
    row["Tobacco_Use"] = detect_binary(general_low, [r"\btobacco\b", r"\bsmoking\b", r"\bcigarette\b", r"\bbeedi\b", r"\bbidi\b", r"\bgutka\b", r"\bgutkha\b", r"\bkhaini\b", r"\bpan masala\b"], [r"\b(no\s+h/o|no\s+history\s+of|denies?)\b.{0,25}\b(tobacco|smoking|cigarette|beedi|bidi|gutka|gutkha|khaini|pan masala)\b"])
    row["Areca_Nut_Use"] = detect_binary(general_low, [r"\bareca\b", r"\bbetel\b", r"\bsupari\b"], [r"\b(no\s+h/o|no\s+history\s+of|denies?)\b.{0,25}\b(areca|betel|supari)\b"])
    row["Alcohol_Use"] = detect_binary(general_low, [r"\balcohol\b", r"\bliquor\b", r"\bbeer\b", r"\bwine\b", r"\bdrinking\b"], [r"\b(no\s+h/o|no\s+history\s+of|denies?)\b.{0,25}\balcohol\b"])

    if re.search(r"family history\s*[:\-]\s*(yes|present|positive)", general_low):
        row["Family_History"] = "Yes"
    elif re.search(r"family history\s*[:\-]\s*(no|nil|absent|negative)", general_low):
        row["Family_History"] = "No"

    if row["Tobacco_Use"] == "Yes":
        m = re.search(r"((?:tobacco|smoking|cigarette|beedi|bidi|gutka|gutkha|khaini|pan masala)[^\n]{0,100})", general_text, re.I)
        if m:
            row["Tobacco_Use_Details"] = m.group(1).strip(" .,:;-")

    if row["Areca_Nut_Use"] == "Yes":
        m = re.search(r"((?:areca|betel|supari)[^\n]{0,100})", general_text, re.I)
        if m:
            row["Areca_Nut_Details"] = m.group(1).strip(" .,:;-")

    if row["Alcohol_Use"] == "Yes":
        m = re.search(r"(alcohol[^\n]{0,100}|drinking[^\n]{0,100})", general_text, re.I)
        if m:
            row["Alcohol_Use_Details"] = m.group(1).strip(" .,:;-")

    if re.search(r"\bburning sensation\b", oral_low):
        row["Burning_Sensation"] = "Yes"

    if re.search(r"\b(restricted|reduced)\b.{0,20}\bmouth opening\b|\btrismus\b", oral_low):
        row["Mouth_Opening_Status"] = "Restricted"
    elif re.search(r"\bmouth opening\b.{0,15}\bnormal\b", oral_low):
        row["Mouth_Opening_Status"] = "Normal"

    if re.search(r"oral hygiene status\s*[:\-]\s*poor", oral_low) or "calculus +++" in oral_low or "debris +++" in oral_low:
        row["Oral_Hygiene_Status"] = "Poor"
    elif re.search(r"oral hygiene status\s*[:\-]\s*fair", oral_low) or "calculus ++" in oral_low or "debris ++" in oral_low or "calculus +" in oral_low or "debris +" in oral_low:
        row["Oral_Hygiene_Status"] = "Fair"
    elif re.search(r"oral hygiene status\s*[:\-]\s*good", oral_low):
        row["Oral_Hygiene_Status"] = "Good"

    if re.search(r"\bno palpable neck node\b|\bno neck node\b|\bnodes? not palpable\b", oral_low):
        row["Cervical_Lymphadenopathy"] = "Negative"
        row["Cervical_Lymphadenopathy_Details"] = "No palpable neck node"
    elif re.search(r"\blymph node\b|\bsubmandibular node\b|\bneck node\b", oral_low):
        row["Cervical_Lymphadenopathy"] = "Positive"

    if re.search(r"no\s+h/o\s+bleeding|no\s+history\s+of\s+bleeding", oral_low):
        row["Bleeding_Present"] = "No"
        row["Bleeding_Details"] = "No H/o bleeding"
    elif re.search(r"\bbleeding\b", oral_low):
        row["Bleeding_Present"] = "Yes"

    return row


def normalize_yes_no(value: str) -> str:
    v = str(value).strip().lower()
    if v in {"yes", "y", "1", "true", "present", "positive"}:
        return "Yes"
    if v in {"no", "n", "0", "false", "absent", "negative"}:
        return "No"
    return value


def clean_output_row(row: Dict[str, Any]) -> Dict[str, str]:
    clean: Dict[str, str] = {}
    for col in COLUMNS:
        val = row.get(col, "Not documented")
        if isinstance(val, list):
            val = "; ".join(str(v) for v in val)
        val = str(val).strip()

        if col == "Sex":
            lut = {"M": "Male", "F": "Female", "m": "Male", "f": "Female", "male": "Male", "female": "Female"}
            val = lut.get(val, lut.get(val.lower(), val))
            if val not in ("Male", "Female", "Not documented"):
                val = "Not documented"

        if col in YES_NO_FIELDS:
            val = normalize_yes_no(val)

        if col == "Cervical_Lymphadenopathy":
            low = val.lower()
            if low in {"yes", "positive", "present", "1"}:
                val = "Positive"
            elif low in {"no", "negative", "absent", "0"}:
                val = "Negative"

        if col == "Mouth_Opening_Status":
            low = val.lower()
            if "restrict" in low or "reduced" in low or "trismus" in low:
                val = "Restricted"
            elif "normal" in low:
                val = "Normal"
            elif val != "Not documented":
                val = "Not documented"

        if col == "Oral_Hygiene_Status":
            low = val.lower()
            if "poor" in low:
                val = "Poor"
            elif "fair" in low:
                val = "Fair"
            elif "good" in low:
                val = "Good"
            elif val != "Not documented":
                val = "Not documented"

        clean[col] = "Not documented" if val in {"", "None", "nan", "[]", "{}"} else val
    return clean


def post_validate_row(row: Dict[str, str]) -> Dict[str, str]:
    row = dict(row)

    age_txt = str(row.get("Age", "")).strip()
    if age_txt.isdigit():
        age = int(age_txt)
        if not (1 <= age <= 120):
            row["Age"] = "Not documented"
    elif age_txt != "Not documented":
        row["Age"] = "Not documented"

    node_details = str(row.get("Cervical_Lymphadenopathy_Details", "")).lower()
    if any(x in node_details for x in ["no palpable", "no neck node", "absent", "not palpable"]):
        row["Cervical_Lymphadenopathy"] = "Negative"

    bleeding_details = str(row.get("Bleeding_Details", "")).lower()
    if any(x in bleeding_details for x in ["no h/o bleeding", "no history of bleeding", "bleeding absent", "no bleeding"]):
        row["Bleeding_Present"] = "No"

    fam_details = str(row.get("Family_History_Details", "")).strip().lower()
    if row.get("Family_History") == "Yes" and fam_details in {"", "not documented", "nrmh", "+ nrmh.", "+nrmh."}:
        row["Family_History"] = "Not documented"
        row["Family_History_Details"] = "Not documented"

    findings = (str(row.get("Specific_Findings", "")) + " " + str(row.get("Soft_Tissue_Exam", ""))).lower()
    oral = str(row.get("Oral_Hygiene_Status", "")).lower()
    if "calculus +++" in findings or "poor oral hygiene" in findings or "debris +++" in findings:
        row["Oral_Hygiene_Status"] = "Poor"
    elif oral not in {"good", "fair", "poor", "not documented"}:
        row["Oral_Hygiene_Status"] = "Not documented"

    for status_field, detail_field in [
        ("Tobacco_Use", "Tobacco_Use_Details"),
        ("Areca_Nut_Use", "Areca_Nut_Details"),
        ("Alcohol_Use", "Alcohol_Use_Details"),
    ]:
        details = str(row.get(detail_field, "")).lower()
        if row.get(status_field) == "Not documented":
            if any(x in details for x in ["no ", "denies", "absent", "negative"]):
                row[status_field] = "No"
            elif details not in {"", "not documented"}:
                row[status_field] = "Yes"

    return row


def merge_results(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key in COLUMNS:
        old_val = merged.get(key, "Not documented")
        new_val = update.get(key, "Not documented")

        if is_missing(new_val):
            continue
        if is_missing(old_val):
            merged[key] = new_val
            continue

        if key in {"Mouth_Opening_Status", "Oral_Hygiene_Status", "Cervical_Lymphadenopathy"}:
            merged[key] = new_val
            continue

        if len(str(new_val).strip()) > len(str(old_val).strip()):
            merged[key] = new_val
    return merged


def format_snippet(item: Dict[str, Any]) -> str:
    return "[{src}] {txt}".format(src=item["source"], txt=item["text"])


def build_patient_payload(folder_path: str, patient_id: str, max_patient_chars: int) -> Optional[Dict[str, Any]]:
    file_contents = read_files(folder_path)
    if not file_contents:
        print("  [ocr] No .txt files found")
        return None

    # Extract metadata from filenames (Age, Sex, Hospital_No)
    filenames = [fname for fname, _ in file_contents]
    filename_meta = extract_filename_metadata(filenames)
    if filename_meta:
        print("  [preprocess] Filename metadata detected: {meta}".format(meta=filename_meta))

    print("  [ocr] {n} file(s) loaded (after noise filtering)".format(n=len(file_contents)))

    routed = route_pages(file_contents)
    oral_pages = routed["oral"]
    general_pages = routed["general"]
    dropped_pages = routed["dropped"]
    print("  [ocr] oral={o} | general={g} | dropped={d}".format(o=len(oral_pages), g=len(general_pages), d=len(dropped_pages)))

    oral_text_raw = "\n\n".join("=== {fname} ===\n{txt}".format(fname=fname, txt=txt) for fname, txt in oral_pages).strip()
    general_text_raw = "\n\n".join("=== {fname} ===\n{txt}".format(fname=fname, txt=txt) for fname, txt in general_pages).strip()

    if not oral_text_raw and not general_text_raw:
        print("  [ocr] No useful text survived routing")
        return None

    oral_budget = max(3000, int(max_patient_chars * 0.55))
    general_budget = max(1800, int(max_patient_chars * 0.25))
    cluster_budget = max(1200, max_patient_chars - oral_budget - general_budget)

    oral_snippets = split_into_snippets(oral_pages)
    general_snippets = split_into_snippets(general_pages)
    all_snippets = oral_snippets + [s for s in general_snippets if s not in oral_snippets]
    clusters = build_clusters(all_snippets)

    field_packets: Dict[str, List[str]] = {}
    for field in COLUMNS:
        if field == "Patient_ID":
            continue
        ranked = rank_snippets_for_field(field, all_snippets, clusters, max_items=3)
        if ranked:
            field_packets[field] = [format_snippet(item) for item in ranked]

    cluster_text = "\n".join(
        "- {label} :: {summary} :: {src}".format(
            label=cluster["label"], summary=cluster["summary"], src=cluster["source_hint"]
        )
        for cluster in clusters[:8]
    )
    cluster_text, _ = controlled_truncate(cluster_text, cluster_budget)

    oral_text, oral_truncated = controlled_truncate(oral_text_raw, oral_budget)
    general_text, general_truncated = controlled_truncate(general_text_raw, general_budget)

    prefill = cheap_prefill(patient_id, oral_text, general_text, filename_meta=filename_meta)

    packet_lines: List[str] = []
    for field in COLUMNS:
        if field == "Patient_ID":
            continue
        evidences = field_packets.get(field)
        if evidences:
            packet_lines.append("{field}:".format(field=field))
            packet_lines.extend("  - {item}".format(item=item) for item in evidences)
    field_evidence_text = "\n".join(packet_lines)

    prompt_char_estimate = len(oral_text) + len(general_text) + len(cluster_text) + len(field_evidence_text) + 1400

    return {
        "patient_id": patient_id,
        "prefill": prefill,
        "oral_text": oral_text,
        "general_text": general_text,
        "cluster_text": cluster_text,
        "field_evidence_text": field_evidence_text,
        "prompt_char_estimate": prompt_char_estimate,
        "truncated": oral_truncated or general_truncated,
    }


def make_single_prompt(patient_payloads: List[Dict[str, Any]]) -> str:
    schema_hint = {col: "Not documented" for col in COLUMNS}
    sections: List[str] = []

    for payload in patient_payloads:
        pid = payload["patient_id"]
        sections.append(
            "\n".join(
                [
                    PATIENT_START_TEMPLATE.format(patient_id=pid),
                    "CURRENT_PREFILL_JSON:",
                    json.dumps(payload["prefill"], ensure_ascii=False),
                    "SALIENT_SIMILARITY_CLUSTERS:",
                    payload["cluster_text"] if payload["cluster_text"] else "Not documented",
                    "FIELD_EVIDENCE_PACKETS:",
                    payload["field_evidence_text"] if payload["field_evidence_text"] else "Not documented",
                    "ORAL_TEXT:",
                    payload["oral_text"] if payload["oral_text"] else "Not documented",
                    "GENERAL_TEXT:",
                    payload["general_text"] if payload["general_text"] else "Not documented",
                    PATIENT_END_TEMPLATE.format(patient_id=pid),
                ]
            )
        )

    return """You are a medical data extraction specialist for oral case sheets.
You will receive multiple patients in ONE request.
Each patient is strictly isolated inside a unique delimiter block.
Never mix patients.

Rules:
{rules}

Output contract:
- Return exactly one valid JSON object.
- The top-level key must be: patients
- Include one patient object for every patient block.
- Patient_ID must exactly match the delimiter ID.
- The fields object must contain all 39 fixed fields exactly once.
- patient_summary should be a short clinically useful summary.
- extra_findings should capture important details that do not fit cleanly into the 39 fields.
- evidence_map should contain short field-linked evidence snippets with source hints.
- No markdown. No explanation. JSON only.

Example fields skeleton:
{schema}

Patients to analyze:
{patients}
""".format(
        rules=EXTRACTION_RULES,
        schema=json.dumps(schema_hint, ensure_ascii=False),
        patients="\n".join(sections),
    ).strip()


def normalize_model_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for col in COLUMNS:
        normalized[col] = fields.get(col, "Not documented")
    return normalized


def validate_response(response: Any, expected_patient_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    parsed: Dict[str, Dict[str, Any]] = {}
    if not isinstance(response, dict):
        return parsed

    patients = response.get("patients")
    if not isinstance(patients, list):
        return parsed

    expected = set(expected_patient_ids)
    for item in patients:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("Patient_ID", "")).strip()
        fields = item.get("fields")
        if pid in expected and isinstance(fields, dict):
            parsed[pid] = {
                "fields": normalize_model_fields(fields),
                "patient_summary": str(item.get("patient_summary", "")).strip() or "Not documented",
                "extra_findings": item.get("extra_findings", []) if isinstance(item.get("extra_findings"), list) else [],
                "evidence_map": item.get("evidence_map", []) if isinstance(item.get("evidence_map"), list) else [],
            }
    return parsed


def flatten_extra_findings(patient_id: str, findings: Sequence[Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "Patient_ID": patient_id,
                "Category": str(item.get("category", "")).strip() or "Other",
                "Title": str(item.get("title", "")).strip() or "Untitled",
                "Detail": str(item.get("detail", "")).strip() or "Not documented",
                "Evidence": str(item.get("evidence", "")).strip() or "Not documented",
                "Source_Hint": str(item.get("source_hint", "")).strip() or "Not documented",
            }
        )
    return rows


def flatten_evidence_map(patient_id: str, evidence_items: Sequence[Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip()
        if field and field not in COLUMNS:
            continue
        rows.append(
            {
                "Patient_ID": patient_id,
                "Field": field or "Unknown",
                "Evidence": str(item.get("evidence", "")).strip() or "Not documented",
                "Source_Hint": str(item.get("source_hint", "")).strip() or "Not documented",
            }
        )
    return rows


def run(patients_dir: str, output_csv: str, output_xlsx: str, output_json: str, max_patient_chars: int, model: str, batch_size: int = 1, use_cache: bool = True) -> None:
    if not os.path.exists(patients_dir):
        print("\n❌ Error: The directory '{path}' does not exist.".format(path=patients_dir))
        print("   Make sure you are running the script from the correct folder (IAI-PROJECT-main) or provide the --folder argument.")
        return

    subfolders = sorted(d for d in os.listdir(patients_dir) if os.path.isdir(os.path.join(patients_dir, d)))
    if not subfolders:
        print("\n❌ No patient folders found in: {path}".format(path=patients_dir))
        return

    print("\n[ocr] Found {n} patient folder(s)".format(n=len(subfolders)))

    patient_payloads: List[Dict[str, Any]] = []
    rows_by_patient: Dict[str, Dict[str, str]] = {}
    extra_rows: List[Dict[str, str]] = []
    evidence_rows: List[Dict[str, str]] = []
    summary_rows: List[Dict[str, str]] = []

    for i, folder_name in enumerate(subfolders, start=1):
        folder_path = os.path.join(patients_dir, folder_name)
        print("\n" + "=" * 55)
        print("[ocr] Preparing patient {i}/{n}: {name}".format(i=i, n=len(subfolders), name=folder_name))

        payload = build_patient_payload(folder_path, folder_name, max_patient_chars=max_patient_chars)
        if payload is None:
            print("  [ocr] Skipping — no valid payload")
            continue

        if payload["truncated"]:
            print("  [ocr] Text was truncated locally for token control")

        patient_payloads.append(payload)
        rows_by_patient[folder_name] = post_validate_row(clean_output_row(payload["prefill"]))

    if not patient_payloads:
        print("\n❌ No valid patient payloads prepared.")
        return

    parsed: Dict[str, Dict[str, Any]] = {}
    master_response = {"patients": []}
    
    # Process in batches to maintain extraction quality
    for i in range(0, len(patient_payloads), batch_size):
        batch = patient_payloads[i:i + batch_size]
        batch_ids = [p["patient_id"] for p in batch]
        prompt = make_single_prompt(batch)
        
        print("\n" + "-" * 55)
        print("[ocr] Sending Gemini request for batch {b_idx}/{total_b}: {ids}".format(
            b_idx=(i // batch_size) + 1, 
            total_b=(len(patient_payloads) + batch_size - 1) // batch_size, 
            ids=batch_ids
        ))
        
        response = call_llm(prompt, response_schema=RESPONSE_SCHEMA, model=model, temperature=0.0, use_cache=use_cache)
        
        if response and "patients" in response:
            master_response["patients"].extend(response["patients"])
            
            # Structural sanity check for bad data (hallucinated sparse data)
            for pt in response.get("patients", []):
                pid = pt.get("Patient_ID")
                fields = pt.get("fields", {})
                if not isinstance(fields, dict):
                    continue
                    
                not_doc_count = sum(1 for v in fields.values() if str(v).lower() in {"not documented", "none", "", "{}"})
                if not_doc_count >= 36:
                    print("  [WARNING] Patient {pid} returned severely sparse data ({n}/39 fields). Quality may be compromised.".format(pid=pid, n=not_doc_count))
                    
            parsed.update(validate_response(response, batch_ids))
        else:
            print("  [ERROR] Empty or invalid response for batch: {ids}".format(ids=batch_ids))
            
    if master_response["patients"]:
        os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(master_response, f, ensure_ascii=False, indent=2)
        print("  [ocr] Raw structured aggregated JSON saved → {path}".format(path=output_json))

    for payload in patient_payloads:
        pid = payload["patient_id"]
        model_packet = parsed.get(pid, {})
        merged = merge_results(rows_by_patient[pid], model_packet.get("fields", {}))
        rows_by_patient[pid] = post_validate_row(clean_output_row(merged))

        for row in flatten_extra_findings(pid, model_packet.get("extra_findings", [])):
            extra_rows.append(row)
        for row in flatten_evidence_map(pid, model_packet.get("evidence_map", [])):
            evidence_rows.append(row)
        summary_rows.append(
            {
                "Patient_ID": pid,
                "Patient_Summary": str(model_packet.get("patient_summary", "Not documented")) or "Not documented",
            }
        )

        filled = sum(1 for v in rows_by_patient[pid].values() if v != "Not documented")
        print("  [ocr] {pid}: {filled}/{total} fixed fields filled".format(pid=pid, filled=filled, total=len(COLUMNS)))
        print("  [ocr] Diagnosis: {txt}".format(txt=rows_by_patient[pid]["Clinical_Diagnosis"][:100]))

    df = pd.DataFrame([rows_by_patient[pid] for pid in sorted(rows_by_patient)], columns=COLUMNS)
    df.to_csv(output_csv, index=False)

    extras_df = pd.DataFrame(extra_rows, columns=["Patient_ID", "Category", "Title", "Detail", "Evidence", "Source_Hint"])
    evidence_df = pd.DataFrame(evidence_rows, columns=["Patient_ID", "Field", "Evidence", "Source_Hint"])
    summary_df = pd.DataFrame(summary_rows, columns=["Patient_ID", "Patient_Summary"])

    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="main_39_fields", index=False)
        summary_df.to_excel(writer, sheet_name="patient_summaries", index=False)
        extras_df.to_excel(writer, sheet_name="extra_findings", index=False)
        evidence_df.to_excel(writer, sheet_name="evidence_map", index=False)

    print("\n" + "=" * 55)
    print("✅ DONE")
    print("   Patients   : {n}".format(n=len(df)))
    print("   Fixed cols : {n}".format(n=len(COLUMNS)))
    print("   CSV        : {p}".format(p=output_csv))
    print("   Excel      : {p}".format(p=output_xlsx))
    print("   JSON       : {p}".format(p=output_json))
    print("\nPreview:")
    preview_cols = [
        "Patient_ID",
        "Age",
        "Sex",
        "HTN",
        "DM",
        "Tobacco_Use",
        "Oral_Hygiene_Status",
        "Clinical_Diagnosis",
        "Final_Provisional_Dx",
    ]
    print(df[preview_cols].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default="data/patients")
    parser.add_argument("--output", default="data/output_patients.csv")
    parser.add_argument("--excel", default="data/output_patients.xlsx")
    parser.add_argument("--json", default="data/output_patients_full.json")
    parser.add_argument("--max-patient-chars", type=int, default=12000, help="Approx chars kept per patient after routing and evidence packing")
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    parser.add_argument("--batch-size", type=int, default=3, help="Patients processed per API request (default 3 to batch all in one call)")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching mechanism to prevent poisoning from previous bad runs")
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)
    run(
        patients_dir=args.folder,
        output_csv=args.output,
        output_xlsx=args.excel,
        output_json=args.json,
        max_patient_chars=args.max_patient_chars,
        model=args.model,
        batch_size=args.batch_size,
        use_cache=not args.no_cache,
    )

