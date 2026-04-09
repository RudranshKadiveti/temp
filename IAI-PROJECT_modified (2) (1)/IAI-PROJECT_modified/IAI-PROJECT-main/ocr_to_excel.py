import argparse
import json
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

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

MISSING_VALUES = {
    "",
    "not documented",
    "none",
    "nan",
    "[]",
    "{}",
    "null",
    "not mentioned",
}

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
- You are analyzing exactly one patient.
- Use exact field names for the 39 fixed fields.
- Use "Not documented" when evidence is absent or too weak.
- Never invent values.
- Prefer oral/maxillofacial/pathology evidence for lesion-related fields.
- Prefer general history/demographic evidence for age, sex, comorbidities, and habits.
- If two snippets conflict, prefer the more specific snippet with clearer wording.
- Use the provided evidence packets first, then the routed text.
- Keep extra important findings in extra_findings even if they do not fit neatly into the 39 fixed fields.
- Keep evidence_map concise and field-linked.

Normalization rules:
- Sex -> Male / Female / Not documented.
- HTN, DM, Family_History, Burning_Sensation, Bleeding_Present, Tobacco_Use, Areca_Nut_Use, Alcohol_Use -> Yes / No / Not documented.
- Mouth_Opening_Status -> Normal / Restricted / Not documented.
- Oral_Hygiene_Status -> Good / Fair / Poor / Not documented.
- Cervical_Lymphadenopathy -> Positive / Negative / Not documented.
- Family history must come from explicit family-history text, not generic past history.
- Bleeding_Present refers to oral complaint context, not unrelated GI bleeding.
""".strip()


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

SINGLE_PATIENT_RESPONSE_SCHEMA = {
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


def is_missing(value: Any) -> bool:
    return str(value).strip().lower() in MISSING_VALUES


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


def read_files(folder_path: str) -> List[Tuple[str, str]]:
    files = sorted(f for f in os.listdir(folder_path) if f.endswith(".txt"))
    result: List[Tuple[str, str]] = []
    for fname in files:
        path = os.path.join(folder_path, fname)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            txt = dedupe_lines(normalize_spaces(f.read()))
            result.append((fname, txt))
    return result


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
        oral_pages = [(fname, txt) for fname, txt, _, _, _ in ranked[:min(3, len(ranked))]]

    if not general_pages and scored_rows:
        ranked = sorted(scored_rows, key=lambda x: (x[3], x[2], -x[4], len(x[1])), reverse=True)
        general_pages = [(fname, txt) for fname, txt, _, _, _ in ranked[:min(3, len(ranked))]]

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


def cluster_label(items: List[Dict[str, Any]]) -> str:
    bag: Dict[str, int] = defaultdict(int)
    for item in items[:4]:
        for term in GLOBAL_MEDICAL_TERMS:
            if term in item["low"]:
                bag[term] += 1

    if not bag:
        return "general evidence"

    return ", ".join([term for term, _ in sorted(bag.items(), key=lambda kv: (-kv[1], kv[0]))[:3]])


def build_clusters(snippets: List[Dict[str, Any]], max_clusters: int = 16) -> List[Dict[str, Any]]:
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
        return (
            str(age) if 1 <= age <= 120 else "Not documented",
            "Male" if sex in ("m", "male") else "Female",
        )

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


def cheap_prefill(patient_id: str, oral_text: str, general_text: str) -> Dict[str, str]:
    row = {col: "Not documented" for col in COLUMNS}
    row["Patient_ID"] = patient_id

    combined = (general_text + "\n\n" + oral_text).strip()
    oral_low = oral_text.lower()
    general_low = general_text.lower()

    m = re.search(r"(?:hospital\s*no|registration\s*no|mrd\s*no|uhid|op\s*no)[:\s\-]*([a-z0-9/\-]{3,30})", combined, re.I)
    if m:
        row["Hospital_No"] = m.group(1).strip()

    m_icd = re.search(r"\b([CD]\d{2}(?:\.\d+)?)\b", combined, re.I)
    if m_icd:
        row["ICD_Code"] = m_icd.group(1).upper()

    age, sex = extract_age_sex(combined)
    row["Age"] = age
    row["Sex"] = sex

    row["HTN"] = detect_binary(
        general_low,
        [r"\bhtn\b", r"\bhypertension\b", r"\bantihypertensive\b"],
        [r"\bno\b.{0,20}\b(htn|hypertension)\b"],
    )

    row["DM"] = detect_binary(
        general_low,
        [r"\bdm\b", r"\bdiabetes\b", r"\bdiabetic\b", r"\bmetformin\b", r"\binsulin\b"],
        [r"\bno\b.{0,20}\b(dm|diabetes|diabetic)\b"],
    )

    row["Tobacco_Use"] = detect_binary(
        general_low,
        [r"\btobacco\b", r"\bsmoking\b", r"\bcigarette\b", r"\bbeedi\b", r"\bbidi\b", r"\bgutka\b", r"\bgutkha\b", r"\bkhaini\b", r"\bpan masala\b"],
        [r"\b(no\s+h/o|no\s+history\s+of|denies?)\b.{0,30}\b(tobacco|smoking|cigarette|beedi|bidi|gutka|gutkha|khaini|pan masala)\b"],
    )

    row["Areca_Nut_Use"] = detect_binary(
        general_low,
        [r"\bareca\b", r"\bbetel\b", r"\bsupari\b"],
        [r"\b(no\s+h/o|no\s+history\s+of|denies?)\b.{0,25}\b(areca|betel|supari)\b"],
    )

    row["Alcohol_Use"] = detect_binary(
        general_low,
        [r"\balcohol\b", r"\bliquor\b", r"\bbeer\b", r"\bwine\b", r"\bdrinking\b"],
        [r"\b(no\s+h/o|no\s+history\s+of|denies?)\b.{0,25}\balcohol\b"],
    )

    if re.search(r"family history\s*[:\-]\s*(yes|present|positive)", general_low):
        row["Family_History"] = "Yes"
    elif re.search(r"family history\s*[:\-]\s*(no|nil|absent|negative)", general_low):
        row["Family_History"] = "No"

    m_fh = re.search(r"family history[:\s\-]*([^\n]{1,140})", general_text, re.I)
    if m_fh:
        fh = m_fh.group(1).strip(" .,:;-")
        if fh and fh.lower() not in {"yes", "no", "nil", "absent", "negative", "positive", "present"}:
            row["Family_History_Details"] = fh

    m_cc = re.search(r"(?:chief complaint|complaint|c/o|presents with)[:\s\-]*([^\n]{3,180})", combined, re.I)
    if m_cc:
        row["Chief_Complaint"] = m_cc.group(1).strip(" .,:;-")

    if row["Tobacco_Use"] == "Yes":
        m = re.search(r"((?:tobacco|smoking|cigarette|beedi|bidi|gutka|gutkha|khaini|pan masala)[^\n]{0,120})", general_text, re.I)
        if m:
            row["Tobacco_Use_Details"] = m.group(1).strip(" .,:;-")

    if row["Areca_Nut_Use"] == "Yes":
        m = re.search(r"((?:areca|betel|supari)[^\n]{0,120})", general_text, re.I)
        if m:
            row["Areca_Nut_Details"] = m.group(1).strip(" .,:;-")

    if row["Alcohol_Use"] == "Yes":
        m = re.search(r"(alcohol[^\n]{0,120}|drinking[^\n]{0,120})", general_text, re.I)
        if m:
            row["Alcohol_Use_Details"] = m.group(1).strip(" .,:;-")

    if re.search(r"\bburning sensation\b", oral_low):
        row["Burning_Sensation"] = "Yes"

    m_pain = re.search(r"(pain[^\n]{0,100}|painful[^\n]{0,100}|tenderness[^\n]{0,100}|odynophagia[^\n]{0,100})", oral_text, re.I)
    if m_pain:
        row["Pain_Details"] = m_pain.group(1).strip(" .,:;-")

    if re.search(r"\b(restricted|reduced)\b.{0,25}\bmouth opening\b|\btrismus\b", oral_low):
        row["Mouth_Opening_Status"] = "Restricted"
    elif re.search(r"\bmouth opening\b.{0,15}\bnormal\b", oral_low):
        row["Mouth_Opening_Status"] = "Normal"

    m_mo = re.search(r"(mouth opening[^\n]{0,100}|interincisal[^\n]{0,100}|trismus[^\n]{0,100})", oral_text, re.I)
    if m_mo:
        row["Mouth_Opening_Details"] = m_mo.group(1).strip(" .,:;-")

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
        m_ln = re.search(r"(lymph node[^\n]{0,100}|submandibular node[^\n]{0,100}|neck node[^\n]{0,100})", oral_text, re.I)
        if m_ln:
            row["Cervical_Lymphadenopathy_Details"] = m_ln.group(1).strip(" .,:;-")

    if re.search(r"no\s+h/o\s+bleeding|no\s+history\s+of\s+bleeding", oral_low):
        row["Bleeding_Present"] = "No"
        row["Bleeding_Details"] = "No H/o bleeding"
    elif re.search(r"\bbleeding\b", oral_low):
        row["Bleeding_Present"] = "Yes"
        m_bleed = re.search(r"(bleeding[^\n]{0,100})", oral_text, re.I)
        if m_bleed:
            row["Bleeding_Details"] = m_bleed.group(1).strip(" .,:;-")

    m_dx = re.search(r"(?:clinical diagnosis|diagnosis|impression)[:\s\-]*([^\n]{3,180})", oral_text, re.I)
    if m_dx:
        row["Clinical_Diagnosis"] = m_dx.group(1).strip(" .,:;-")

    m_pdx = re.search(r"(?:provisional diagnosis|final diagnosis|working diagnosis)[:\s\-]*([^\n]{3,180})", oral_text, re.I)
    if m_pdx:
        row["Final_Provisional_Dx"] = m_pdx.group(1).strip(" .,:;-")

    m_ddx = re.search(r"(?:differential diagnosis|differentials?)[:\s\-]*([^\n]{3,180})", oral_text, re.I)
    if m_ddx:
        row["Differential_Diagnosis"] = m_ddx.group(1).strip(" .,:;-")

    m_tnm = re.search(r"\b(T[0-4X][A-Z]?(?:\s*)N[0-3X][A-Z]?(?:\s*)M[0-1X])\b", combined, re.I)
    if m_tnm:
        row["TNM_Stage"] = re.sub(r"\s+", "", m_tnm.group(1).upper())

    m_hist = re.search(r"(well differentiated|moderately differentiated|poorly differentiated)", combined, re.I)
    if m_hist:
        row["Histological_Subgroup"] = m_hist.group(1).strip().title()

    m_biopsy = re.search(r"(?:biopsy|histopath|hpe|fnac|incisional biopsy)[:\s\-]*([^\n]{3,180})", combined, re.I)
    if m_biopsy:
        row["Biopsy_Details"] = m_biopsy.group(1).strip(" .,:;-")

    m_inv = re.search(r"(?:investigation|investigations)[:\s\-]*([^\n]{3,180})", combined, re.I)
    if m_inv:
        row["Investigations"] = m_inv.group(1).strip(" .,:;-")

    m_plan = re.search(r"(?:treatment plan|plan|advised)[:\s\-]*([^\n]{3,180})", combined, re.I)
    if m_plan:
        row["Treatment_Plan"] = m_plan.group(1).strip(" .,:;-")

    lesion_types = ["ulcer", "growth", "patch", "plaque", "swelling", "mass", "lesion"]
    for token in lesion_types:
        if re.search(rf"\b{re.escape(token)}\b", oral_low):
            row["Lesion_Type"] = token.title()
            break

    color_map = {
        "erythematous": "Red",
        "red": "Red",
        "white": "White",
        "mixed": "Mixed",
        "pale": "Pale",
        "blanched": "Pale",
    }
    for token, norm in color_map.items():
        if re.search(rf"\b{re.escape(token)}\b", oral_low):
            row["Lesion_Color"] = norm
            break

    site_tokens = ["buccal mucosa", "tongue", "palate", "retromolar", "gingiva", "vestibule", "commissure", "faucial pillar"]
    for site in site_tokens:
        if site in oral_low:
            row["Lesion_Site"] = site.title()
            break

    m_soft = re.search(r"(?:soft tissue|mucosa|buccal mucosa|tongue|palate|gingiva)[^\n]{0,180}", oral_text, re.I)
    if m_soft:
        row["Soft_Tissue_Exam"] = m_soft.group(0).strip(" .,:;-")

    m_find = re.search(r"(?:induration|ulcer|growth|tenderness|surface|margin)[^\n]{0,180}", oral_text, re.I)
    if m_find:
        row["Specific_Findings"] = m_find.group(0).strip(" .,:;-")

    m_trauma = re.search(r"(sharp tooth[^\n]{0,120}|trauma[^\n]{0,120}|irritation[^\n]{0,120}|frictional[^\n]{0,120}|cheek bite[^\n]{0,120}|tooth irritation[^\n]{0,120})", combined, re.I)
    if m_trauma:
        row["Trauma_Irritation_History"] = m_trauma.group(1).strip(" .,:;-")

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

    icd = str(row.get("ICD_Code", "")).strip().upper()
    if icd not in {"", "NOT DOCUMENTED"}:
        m = re.match(r"^[CD]\d{2}(?:\.\d+)?$", icd)
        row["ICD_Code"] = icd if m else "Not documented"

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

    always_replace_if_present = {
        "Clinical_Diagnosis",
        "Final_Provisional_Dx",
        "Differential_Diagnosis",
        "Investigations",
        "Biopsy_Details",
        "Treatment_Plan",
        "Specific_Findings",
        "Soft_Tissue_Exam",
        "Chief_Complaint",
        "Histological_Subgroup",
        "TNM_Stage",
        "ICD_Code",
    }

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

        if key in always_replace_if_present:
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

    print("  [ocr] {n} file(s) loaded".format(n=len(file_contents)))

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

    oral_budget = max(4500, int(max_patient_chars * 0.55))
    general_budget = max(2200, int(max_patient_chars * 0.25))
    cluster_budget = max(1400, max_patient_chars - oral_budget - general_budget)

    oral_snippets = split_into_snippets(oral_pages)
    general_snippets = split_into_snippets(general_pages)
    all_snippets = oral_snippets + [s for s in general_snippets if s not in oral_snippets]
    clusters = build_clusters(all_snippets)

    field_packets: Dict[str, List[str]] = {}
    for field in COLUMNS:
        if field == "Patient_ID":
            continue
        ranked = rank_snippets_for_field(field, all_snippets, clusters, max_items=4)
        if ranked:
            field_packets[field] = [format_snippet(item) for item in ranked]

    cluster_text = "\n".join(
        "- {label} :: {summary} :: {src}".format(
            label=cluster["label"],
            summary=cluster["summary"],
            src=cluster["source_hint"],
        )
        for cluster in clusters[:10]
    )
    cluster_text, _ = controlled_truncate(cluster_text, cluster_budget)

    oral_text, oral_truncated = controlled_truncate(oral_text_raw, oral_budget)
    general_text, general_truncated = controlled_truncate(general_text_raw, general_budget)

    prefill = cheap_prefill(patient_id, oral_text, general_text)

    packet_lines: List[str] = []
    for field in COLUMNS:
        if field == "Patient_ID":
            continue
        evidences = field_packets.get(field)
        if evidences:
            packet_lines.append("{field}:".format(field=field))
            packet_lines.extend("  - {item}".format(item=item) for item in evidences)

    field_evidence_text = "\n".join(packet_lines)

    return {
        "patient_id": patient_id,
        "prefill": prefill,
        "oral_text": oral_text,
        "general_text": general_text,
        "cluster_text": cluster_text,
        "field_evidence_text": field_evidence_text,
        "truncated": oral_truncated or general_truncated,
    }


def make_patient_prompt(payload: Dict[str, Any]) -> str:
    pid = payload["patient_id"]
    schema_hint = {col: "Not documented" for col in COLUMNS}

    return f"""
You are a medical data extraction specialist for oral case sheets.

You are analyzing EXACTLY ONE patient.
Never invent facts.
Never use one field to hallucinate another.
Prefer explicit evidence.
If evidence is weak or missing, write "Not documented".

Rules:
{EXTRACTION_RULES}

Output contract:
- Return exactly one valid JSON object.
- No markdown.
- No explanation.
- JSON only.
- Patient_ID must be exactly "{pid}".
- The "fields" object must contain all 39 fixed fields exactly once.
- patient_summary should be short and clinically useful.
- extra_findings should include useful findings that do not fit neatly into the 39 columns.
- evidence_map should contain concise field-linked evidence.

Example fields skeleton:
{json.dumps(schema_hint, ensure_ascii=False)}

PATIENT_BLOCK_START
Patient_ID: {pid}

CURRENT_PREFILL_JSON:
{json.dumps(payload["prefill"], ensure_ascii=False)}

SALIENT_SIMILARITY_CLUSTERS:
{payload["cluster_text"] if payload["cluster_text"] else "Not documented"}

FIELD_EVIDENCE_PACKETS:
{payload["field_evidence_text"] if payload["field_evidence_text"] else "Not documented"}

ORAL_TEXT:
{payload["oral_text"] if payload["oral_text"] else "Not documented"}

GENERAL_TEXT:
{payload["general_text"] if payload["general_text"] else "Not documented"}

PATIENT_BLOCK_END
""".strip()


def normalize_model_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for col in COLUMNS:
        normalized[col] = fields.get(col, "Not documented")
    return normalized


def validate_single_patient_response(response: Any, expected_patient_id: str) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return {}

    pid = str(response.get("Patient_ID", "")).strip()
    fields = response.get("fields")

    if pid != expected_patient_id:
        return {}

    if not isinstance(fields, dict):
        return {}

    return {
        "fields": normalize_model_fields(fields),
        "patient_summary": str(response.get("patient_summary", "")).strip() or "Not documented",
        "extra_findings": response.get("extra_findings", []) if isinstance(response.get("extra_findings"), list) else [],
        "evidence_map": response.get("evidence_map", []) if isinstance(response.get("evidence_map"), list) else [],
    }


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


def call_patient_model(payload: Dict[str, Any], model: str) -> Tuple[Any, Dict[str, Any]]:
    pid = payload["patient_id"]
    prompt = make_patient_prompt(payload)

    print(f"  [ocr] Sending 1 Gemini call for {pid}")

    try:
        response = call_llm(
            prompt,
            response_schema=SINGLE_PATIENT_RESPONSE_SCHEMA,
            model=model,
            temperature=0.0,
            use_cache=True,
        )
    except Exception as e:
        print(f"  [ocr] LLM call failed for {pid}: {e}")
        return None, {}

    parsed = validate_single_patient_response(response, pid)
    if not parsed:
        print(f"  [ocr] Invalid/empty structured response for {pid}")
        return response, {}

    return response, parsed


def run(
    patients_dir: str,
    output_csv: str,
    output_xlsx: str,
    output_json: str,
    max_patient_chars: int,
    model: str,
) -> None:
    subfolders = sorted(d for d in os.listdir(patients_dir) if os.path.isdir(os.path.join(patients_dir, d)))
    if not subfolders:
        print("\n❌ No patient folders found in: {path}".format(path=patients_dir))
        return

    print("\n[ocr] Found {n} patient folder(s)".format(n=len(subfolders)))

    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(output_xlsx) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)

    rows_by_patient: Dict[str, Dict[str, str]] = {}
    extra_rows: List[Dict[str, str]] = []
    evidence_rows: List[Dict[str, str]] = []
    summary_rows: List[Dict[str, str]] = []
    raw_json_rows: List[Dict[str, Any]] = []

    prepared_payloads: List[Dict[str, Any]] = []

    for i, folder_name in enumerate(subfolders, start=1):
        folder_path = os.path.join(patients_dir, folder_name)

        print("\n" + "=" * 60)
        print("[ocr] Preparing patient {i}/{n}: {name}".format(i=i, n=len(subfolders), name=folder_name))

        payload = build_patient_payload(folder_path, folder_name, max_patient_chars=max_patient_chars)
        if payload is None:
            print("  [ocr] Skipping — no valid payload")
            continue

        if payload["truncated"]:
            print("  [ocr] Text was truncated locally for token control")

        prepared_payloads.append(payload)
        rows_by_patient[folder_name] = post_validate_row(clean_output_row(payload["prefill"]))

    if not prepared_payloads:
        print("\n❌ No valid patient payloads prepared.")
        return

    for idx, payload in enumerate(prepared_payloads, start=1):
        pid = payload["patient_id"]

        print("\n" + "-" * 60)
        print("[ocr] LLM patient {i}/{n}: {pid}".format(i=idx, n=len(prepared_payloads), pid=pid))

        raw_response, parsed = call_patient_model(payload, model=model)

        raw_json_rows.append(
            {
                "Patient_ID": pid,
                "raw_response": raw_response,
            }
        )

        if parsed:
            merged = merge_results(rows_by_patient[pid], parsed.get("fields", {}))
            rows_by_patient[pid] = post_validate_row(clean_output_row(merged))

            for row in flatten_extra_findings(pid, parsed.get("extra_findings", [])):
                extra_rows.append(row)

            for row in flatten_evidence_map(pid, parsed.get("evidence_map", [])):
                evidence_rows.append(row)

            summary_rows.append(
                {
                    "Patient_ID": pid,
                    "Patient_Summary": str(parsed.get("patient_summary", "Not documented")) or "Not documented",
                }
            )
        else:
            summary_rows.append(
                {
                    "Patient_ID": pid,
                    "Patient_Summary": "Not documented",
                }
            )

        filled = sum(1 for v in rows_by_patient[pid].values() if v != "Not documented")
        print("  [ocr] {pid}: {filled}/{total} fixed fields filled".format(pid=pid, filled=filled, total=len(COLUMNS)))
        print("  [ocr] Diagnosis: {txt}".format(txt=rows_by_patient[pid]["Clinical_Diagnosis"][:120]))

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

    json_payload = {
        "patients": raw_json_rows,
        "final_rows": df.to_dict(orient="records"),
        "patient_summaries": summary_rows,
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
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
    parser.add_argument(
        "--max-patient-chars",
        type=int,
        default=14000,
        help="Approx chars kept per patient after routing and evidence packing",
    )
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)

    run(
        patients_dir=args.folder,
        output_csv=args.output,
        output_xlsx=args.excel,
        output_json=args.json,
        max_patient_chars=args.max_patient_chars,
        model=args.model,
    )
