# ============================================================
#  config.py  —  EDIT THIS FILE FIRST before running anything
# ============================================================

# ── Get your FREE OpenRouter key (no credit card needed)
#    Sign up at: https://openrouter.ai → Keys → Create Key
#OPENROUTER_API_KEY = "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"
#OPENROUTER_API_KEY = "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"
# Add this to your config.py
GEMINI_API_KEY = "AIzaSyAx_iCtaXyTJMjQjbX0kGx-z47njvIlxQk" # illi nin gemini api key add madu. 
# ── Free models to rotate through (all $0.00 per token)
#    If one hits a rate limit, the next one is tried automatically
'''OPENROUTER_FREE_MODELS = [
      "openrouter/free" # dynamic free model routing 
]'''

# ── OpenRouter free-tier stability controls
#    Helps avoid bursty 429s when many OCR chunks are processed quickly.
#OPENROUTER_MIN_REQUEST_GAP_SEC = 2
#OPENROUTER_MAX_RETRIES_PER_MODEL = 1
#OPENROUTER_BASE_BACKOFF_SEC = 4

# ── File paths (don't change these)
OCR_FOLDER  = "data/ocr"            # put your .txt OCR files here
OUTPUT_FILE = "data/output.csv"     # final ML-ready CSV
CACHE_FILE  = "data/cache.json"     # data-level cache
EXCEL_PATH  = "data/reference.xlsx" # column schema for medical mode

# ── Scraper settings
MAX_RETRIES     = 5    # self-healing retry attempts
REQUEST_TIMEOUT = 30   # seconds per page load
