# ============================================================
# llm_client.py
# Safe direct Gemini API client using requests
# Backward compatible with old pipeline + compatible with new advanced OCR pipeline
# ============================================================
import hashlib
import json
import os
import sqlite3
import threading
import time
from typing import Any

import requests

from config import GEMINI_API_KEY

_PROMPT_CACHE_FILE_OLD = "data/prompt_cache.json"
_PROMPT_CACHE_DB = "data/prompt_cache.db"

DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MIN_REQUEST_GAP_SEC = 4.2

_throttle_lock = threading.Lock()
_next_request_at = 0.0

def _get_db_connection() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(_PROMPT_CACHE_DB, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT)")
    return conn

_db_conn = _get_db_connection()

def _migrate_old_cache() -> None:
    if os.path.exists(_PROMPT_CACHE_FILE_OLD):
        try:
            with open(_PROMPT_CACHE_FILE_OLD, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                print(f"  [Cache DB] Migrating {len(data)} old JSON cache entries to SQLite...")
                with _db_conn:
                    _db_conn.executemany(
                        "INSERT OR IGNORE INTO cache (key, value) VALUES (?, ?)",
                        [(k, v) for k, v in data.items()]
                    )
            os.rename(_PROMPT_CACHE_FILE_OLD, _PROMPT_CACHE_FILE_OLD + ".bak")
            print("  [Cache DB] Migration complete.")
        except Exception as e:
            print(f"  [Cache DB] Migration failed: {e}")

_migrate_old_cache()

def get_from_cache(key: str) -> str | None:
    cursor = _db_conn.execute("SELECT value FROM cache WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None

def save_to_cache(key: str, value: str) -> None:
    with _db_conn:
        _db_conn.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (key, value))

def _throttle_if_needed() -> None:
    global _next_request_at
    with _throttle_lock:
        now = time.time()
        if now < _next_request_at:
            time.sleep(_next_request_at - now)
        _next_request_at = time.time() + MIN_REQUEST_GAP_SEC


def _extract_json_block(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _count_substantive_values(value: Any) -> int:
    missing = {"", "not documented", "none", "nan", "[]", "{}"}

    if isinstance(value, dict):
        return sum(_count_substantive_values(v) for v in value.values())

    if isinstance(value, list):
        return sum(_count_substantive_values(v) for v in value)

    return 0 if str(value).strip().lower() in missing else 1


def _call_gemini(
    prompt: str,
    *,
    response_schema: dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float = 0.0,
) -> str | None:
    model_name = model or DEFAULT_GEMINI_MODEL
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent?key={GEMINI_API_KEY}"
    )

    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "responseMimeType": "application/json",
    }

    if response_schema is not None:
        generation_config["responseSchema"] = response_schema

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "You are a strict JSON extraction API. "
                        "Return exactly one valid JSON value only. "
                        "No prose. No markdown. No explanation."
                    )
                }
            ]
        },
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }

    headers = {"Content-Type": "application/json"}
    max_retries = 3
    base_backoff = 5

    for attempt in range(1, max_retries + 1):
        response = None
        try:
            _throttle_if_needed()
            response = requests.post(url, json=payload, headers=headers, timeout=180)

            if response.status_code == 429:
                wait_s = base_backoff * attempt
                print(f"  [Gemini] Rate limit hit on {model_name}. Waiting {wait_s}s...")
                time.sleep(wait_s)
                continue

            response.raise_for_status()
            data = response.json()

            candidates = data.get("candidates", [])
            if not candidates:
                print("  [Gemini] No output candidates returned.")
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            content = parts[0].get("text", "") if parts else ""
            content = (content or "").strip()

            if not content:
                print("  [LLM] Gemini returned empty content")
                return None

            print(f"  [LLM] ok: {model_name}")
            return content

        except requests.exceptions.Timeout:
            print(f"  [Gemini] Timeout on {model_name}; retrying...")
            time.sleep(base_backoff)
        except Exception as exc:
            print(f"  [Gemini] Connection error on {model_name}: {exc}")
            if response is not None:
                try:
                    print(f"  [Gemini] Details: {response.text[:500]}")
                except Exception:
                    pass
            time.sleep(base_backoff)

    return None


def call_llm(
    prompt: str,
    response_schema: dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float = 0.0,
    use_cache: bool = True,
) -> Any | None:
    """
    Backward compatible:
      old usage  -> call_llm(prompt)
      new usage  -> call_llm(prompt, response_schema=..., model=..., temperature=..., use_cache=True)
    Returns parsed JSON.
    """
    cache_key_payload = {
        "prompt": prompt,
        "response_schema": response_schema,
        "model": model or DEFAULT_GEMINI_MODEL,
        "temperature": temperature,
    }
    key = hashlib.md5(json.dumps(cache_key_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    if use_cache:
        cached_str = get_from_cache(key)
        if cached_str is not None:
            print("  [LLM] cache hit")
            try:
                return json.loads(cached_str)
            except Exception:
                pass

    raw = _call_gemini(
        prompt,
        response_schema=response_schema,
        model=model,
        temperature=temperature,
    )
    if not raw:
        print("  [LLM] API call failed entirely")
        return None

    cleaned = _extract_json_block(raw)

    try:
        parsed = json.loads(cleaned)
        substantive = _count_substantive_values(parsed)

        # avoid poisoning cache with nearly empty results
        if substantive <= 1:
            print("  [LLM] sparse result — not caching to prevent poisoning")
            return parsed

        if use_cache:
            save_to_cache(key, json.dumps(parsed, ensure_ascii=False))

        return parsed
    except Exception as exc:
        print(f"  [LLM] non-JSON content ({exc})")
        print(f"  [LLM] snippet: {cleaned[:800]!r}")
        return None
