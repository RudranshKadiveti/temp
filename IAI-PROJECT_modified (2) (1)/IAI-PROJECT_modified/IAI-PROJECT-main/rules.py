# ============================================================
#  rules.py  —  Post-processing rules for medical OCR data
#  Cleans up common patterns: age/sex combined, binary fields,
#  oral hygiene grading
# ============================================================

def apply_rules(row: dict) -> dict:
    row = _split_age_sex(row)
    row = _fix_binary_fields(row)
    row = _fix_oral_hygiene(row)
    return row


def _split_age_sex(row):
    if "age_sex" in row and row["age_sex"] and "/" in str(row["age_sex"]):
        age, sex = str(row["age_sex"]).split("/", 1)
        try:
            row["age"] = int(age.strip())
            row["sex"] = "Male" if sex.strip().upper() == "M" else "Female"
        except: pass
    return row


def _binary(val):
    if val is None: return None
    v = str(val).lower()
    if any(x in v for x in ["no","absent","negative"]): return 0
    if any(x in v for x in ["+","yes","present","positive"]): return 1
    return None


def _fix_binary_fields(row):
    binary_keywords = ["pain","tobacco","alcohol","burning","bleeding","swelling","ulcer"]
    for key in row:
        if any(kw in key for kw in binary_keywords):
            row[key] = _binary(row[key])
    return row


def _fix_oral_hygiene(row):
    if "oral_hygiene_status" not in row or not row["oral_hygiene_status"]:
        return row
    v = str(row["oral_hygiene_status"])
    row["oral_hygiene_status"] = "poor" if "+++" in v else ("fair" if "+" in v else "good")
    return row