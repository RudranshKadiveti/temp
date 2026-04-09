import asyncio
import uuid
import os
import sys
import traceback
import json
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import pandas as pd

from agents.universal_agent import UniversalScraperAgent
from utils.logger import setup_logger
from utils.data_converter import DataConverter

logger = setup_logger("API_PLATFORM")
load_dotenv()

app = FastAPI(title="Universal Extraction Engine")

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job Tracking
jobs: Dict[str, Dict[str, Any]] = {}

class ScrapeRequest(BaseModel):
    url: str
    query: Optional[str] = None
    pages: int = 5
    min_price: Optional[str] = None
    max_price: Optional[str] = None
    brand: Optional[str] = None
    min_rating: Optional[str] = None
    format: str = "csv"
    headless: bool = True
    debug_snapshots: bool = False


def _normalize_format(fmt: Optional[str]) -> str:
    value = (fmt or "csv").strip().lower()
    aliases = {
        "csv_file": "csv",
        "csvfile": "csv",
        "excel": "xlsx",
    }
    return aliases.get(value, value)


def _supported_formats() -> List[str]:
    return ["csv", "json", "jsonl", "xlsx", "parquet"]


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    return v if v else None


def _clean_api_key(value: Optional[str]) -> Optional[str]:
    v = _blank_to_none(value)
    if not v:
        return None
    if v.lower().startswith("your_") or "your_api_key" in v.lower():
        return None
    return v

def run_scraper_job(job_id: str, request: ScrapeRequest):
    """Background task to run the agent with a fresh event loop to support Windows subprocesses."""
    normalized_query = (request.query or "").strip()
    normalized_min_price = _blank_to_none(request.min_price)
    normalized_max_price = _blank_to_none(request.max_price)
    normalized_brand = _blank_to_none(request.brand)
    normalized_min_rating = _blank_to_none(request.min_rating)

    async def _execute():
        normalized_format = _normalize_format(request.format)
        llm_api_key = _clean_api_key(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"))
        groq_api_key = _clean_api_key(os.getenv("GROQ_API_KEY"))
        agent = UniversalScraperAgent(
            llm_api_key=llm_api_key,
            groq_api_key=groq_api_key,
            llm_model=os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
            groq_model=os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile",
        )
        filters: Dict[str, Any] = {
            "price_min": normalized_min_price,
            "price_max": normalized_max_price,
            "brand": normalized_brand,
            "min_rating": normalized_min_rating,
            "query": normalized_query
        }
        result = await agent.run_task(
            start_url=request.url,
            filters=filters,
            max_pages=request.pages,
            format=normalized_format,
            headless=request.headless,
            debug_snapshots=request.debug_snapshots,
        )
        return result, agent

    try:
        jobs[job_id]["status"] = "processing"
        result, agent = asyncio.run(_execute())

        total_records = int(result.get("total_records", 0) or 0)
        result_output = (result.get("output_path") or "").strip()
        latest_output = str(agent.pipeline.latest_output_path) if agent.pipeline.latest_output_path else ""
        output_path = result_output if result_output and os.path.exists(result_output) else latest_output

        # Jobs with no rows or missing output file are marked failed so dashboard actions stay accurate.
        if total_records <= 0:
            jobs[job_id].update({
                "status": "failed",
                "total_records": 0,
                "pages_visited": result.get("pages_visited", 0),
                "apis_found": len(result.get("api_discovery_log", [])),
                "metrics": result.get("metrics", {}),
                "site_type": result.get("site_type", "unknown"),
                "output_path": None,
                "completed_at": datetime.now().strftime("%H:%M:%S"),
                "error": "No records were extracted. Try a broader query or a different page.",
            })
            return

        if not output_path or not os.path.exists(output_path):
            jobs[job_id].update({
                "status": "failed",
                "total_records": total_records,
                "pages_visited": result.get("pages_visited", 0),
                "apis_found": len(result.get("api_discovery_log", [])),
                "metrics": result.get("metrics", {}),
                "site_type": result.get("site_type", "unknown"),
                "output_path": None,
                "completed_at": datetime.now().strftime("%H:%M:%S"),
                "error": "Extraction finished but output file was not generated.",
            })
            return

        # Update job info
        jobs[job_id].update({
            "status": "completed",
            "total_records": total_records,
            "pages_visited": result.get("pages_visited", 0),
            "apis_found": len(result.get("api_discovery_log", [])),
            "metrics": result.get("metrics", {}),
            "site_type": result.get("site_type", "unknown"),
            "output_path": output_path,
            "completed_at": datetime.now().strftime("%H:%M:%S")
        })
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}\n{traceback.format_exc()}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)

@app.post("/api/scrape")
async def start_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    request.format = _normalize_format(request.format)
    if request.format not in _supported_formats():
        raise HTTPException(status_code=400, detail=f"Unsupported format. Supported: {', '.join(_supported_formats())}")

    normalized_query = (request.query or "").strip()
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "url": request.url,
        "query": normalized_query,
        "format": request.format,
        "status": "queued",
        "total_records": 0,
        "created_at": datetime.now().strftime("%H:%M:%S")
    }
    
    background_tasks.add_task(run_scraper_job, job_id, request)
    return {"job_id": job_id}

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

@app.get("/api/jobs")
async def list_jobs():
    jobs_list = list(jobs.values())
    return sorted(jobs_list, key=lambda x: x["created_at"], reverse=True)[:50]

@app.get("/api/download/{job_id}")
async def download_result(job_id: str, format: str = Query("csv", description="Output format: csv, json, xlsx, parquet")):
    """Download scraped data in requested format."""
    job = jobs.get(job_id)
    if job is None or job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Data not ready. Job must be completed first.")
        
    path = job.get("output_path")
    if path is None or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Output file not found")
    
    format = _normalize_format(format)
    supported_formats = _supported_formats()
    
    if format not in supported_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Supported: {', '.join(supported_formats)}")
    
    # If original format matches requested format, return directly
    original_format = _normalize_format(Path(path).suffix.lstrip('.').lower())
    if original_format == format or (original_format == 'json' and format == 'jsonl'):
        filename = f"{job_id}_{job['site_type'] or 'scrape'}.{format}"
        return FileResponse(path, filename=filename)
    
    # Convert to requested format
    try:
        output_path = Path(path).parent / f"{Path(path).stem}_converted.{format}"
        converted_path = DataConverter.export_to_format(path, format, str(output_path))
        filename = f"{job_id}_{job['site_type'] or 'scrape'}.{format}"
        return FileResponse(converted_path, filename=filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@app.get("/api/preview/{job_id}")
async def preview_data(job_id: str, limit: int = Query(50, ge=1, le=500)):
    """Get JSON preview of scraped data with pagination."""
    job = jobs.get(job_id)
    if job is None or job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Data not ready")
    
    path = job.get("output_path")
    if path is None or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Output file not found")
    
    try:
        file_format = Path(path).suffix.lstrip('.').lower()
        
        if file_format == 'csv':
            preview = DataConverter.get_csv_preview(path, limit)
        elif file_format in ['json', 'jsonl']:
            preview = DataConverter.get_json_preview(path, limit)
        elif file_format == 'xlsx':
            df = pd.read_excel(path, nrows=limit)
            preview = {
                "columns": list(df.columns),
                "row_count": len(df),
                "data": DataConverter._json_safe_records(df),
                "total_columns": len(df.columns)
            }
        elif file_format == 'parquet':
            df = pd.read_parquet(path).head(limit)
            preview = {
                "columns": list(df.columns),
                "row_count": len(df),
                "data": DataConverter._json_safe_records(df),
                "total_columns": len(df.columns)
            }
        else:
            raise ValueError(f"Unsupported file format: {file_format}")
        
        preview["job_id"] = job_id
        preview["site_type"] = job.get("site_type", "unknown")
        return preview
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@app.get("/api/export/{job_id}")
async def export_data(
    job_id: str, 
    target_format: str = Query("json", description="Target format: csv, json, jsonl, xlsx, parquet")
):
    """Convert and stream data in the requested format."""
    job = jobs.get(job_id)
    if job is None or job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Data not ready")
    
    path = job.get("output_path")
    if path is None or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Output file not found")
    
    target_format = _normalize_format(target_format)
    supported_formats = _supported_formats()
    
    if target_format not in supported_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Supported: {', '.join(supported_formats)}")
    
    try:
        output_path = Path(path).parent / f"{Path(path).stem}_export.{target_format}"
        converted_path = DataConverter.export_to_format(path, target_format, str(output_path))
        filename = f"{job_id}_{job['site_type'] or 'scrape'}.{target_format}"
        return FileResponse(converted_path, filename=filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@app.get("/api/formats/{job_id}")
async def get_available_formats(job_id: str):
    """Get available download formats for a job."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Data not ready")
    
    return {
        "job_id": job_id,
        "available_formats": ["csv", "json", "jsonl", "xlsx", "parquet"],
        "output_path": job.get("output_path"),
        "total_records": job.get("total_records", 0),
        "site_type": job.get("site_type", "unknown")
    }


# Serve the Dashboard (Frontend)
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

# Make sure directories exist
os.makedirs("templates", exist_ok=True)
os.makedirs("data/output", exist_ok=True)
