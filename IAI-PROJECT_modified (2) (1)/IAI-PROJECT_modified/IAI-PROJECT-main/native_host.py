#!/usr/bin/env python3
# ============================================================
#  native_host.py  —  Chrome ↔ Python bridge
#
#  Handles two modes:
#    mode=agent   → runs browser_agent.run_agent()
#    mode=medical → receives file contents from extension,
#                   writes temp files, runs extraction,
#                   returns [{field: value}] for one patient
#
#  SETUP:
#    1. Change the path below to your project folder
#    2. Register com.ai_scraper.host.json with Chrome
# ============================================================
import sys, json, struct, os, tempfile, shutil

# ← EDIT THIS: absolute path to your project folder
sys.path.insert(0, r"D:\IAI Project")

from browser_agent import run_agent
from ocr_to_excel  import read_files, extract_patient


def read_msg():
    raw = sys.stdin.buffer.read(4)
    if not raw: sys.exit(0)
    length = struct.unpack("=I", raw)[0]
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def send_msg(obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(body)))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def handle_agent(req):
    """Web scraping mode — run browser agent."""
    url     = req.get("url", "")
    request = req.get("request", "Extract all data")
    fmt     = req.get("format", "csv")
    pages   = req.get("pages", 10)

    result = run_agent(url, request, max_pages=pages)
    if result:
        send_msg({
            "records": result.get("records", []),
            "summary": result.get("summary", ""),
            "format":  fmt
        })
    else:
        send_msg({"error": "No data extracted."})


def handle_medical(req):
    """
    Medical OCR mode.
    Extension sends file contents directly (no file paths needed).
    We write them to a temp folder, run extraction, delete temp folder.
    """
    patient_id = req.get("patient_id", "patient_001")
    files      = req.get("files", [])   # [{name, content}]
    fmt        = req.get("format", "csv")

    if not files:
        send_msg({"error": "No files received."})
        return

    # Write files to temp directory
    tmpdir = tempfile.mkdtemp(prefix="ocr_")
    try:
        for f in files:
            fname   = f.get("name", "file.txt")
            content = f.get("content", "")
            # Sanitize filename
            fname = os.path.basename(fname)
            with open(os.path.join(tmpdir, fname), "w", encoding="utf-8") as fp:
                fp.write(content)

        # Run extraction
        row = extract_patient(tmpdir, patient_id)

        if row:
            # Return as list with one record (one patient)
            send_msg({
                "records": [row],
                "summary": f"Extracted {sum(1 for v in row.values() if v != 'Not documented')}/39 fields for {patient_id}",
                "format":  fmt
            })
        else:
            send_msg({"error": "Extraction failed — check file contents."})

    except Exception as e:
        send_msg({"error": str(e)})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    req  = read_msg()
    mode = req.get("mode", "agent")
    try:
        if mode == "medical":
            handle_medical(req)
        else:
            handle_agent(req)
    except Exception as e:
        send_msg({"error": str(e)})


if __name__ == "__main__":
    main()