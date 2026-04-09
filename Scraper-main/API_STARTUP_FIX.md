# FIX: How to Start the Scraper API Correctly

The issue was that you were running `python main.py` which is the CLI mode, NOT the API server.

## ✅ CORRECT WAY: Start the API Server

### Option 1: Using the new --api flag (Recommended)
```bash
python main.py --api
```

Server will start at: **http://localhost:8000**

### Option 2: Using uvicorn directly
```bash
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### Option 3: Windows - Double-click run_api.bat
Created a batch script that handles everything:
1. Activates virtual environment
2. Starts Docker containers (if not running)
3. Starts API server

**Just double-click:** `run_api.bat`

---

## Full Setup Process

### 1. **Start Infrastructure** (One time)
```bash
docker-compose up -d postgres redis elasticsearch
```

Wait ~10 seconds for services to initialize.

### 2. **Start API Server** (New window/tab)
```bash
python main.py --api
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete
```

### 3. **Open Dashboard**
Navigate to: **http://localhost:8000**

You should see the Extraction Console dashboard.

### 4. **Test an API Endpoint**
```bash
# In a new terminal
curl http://localhost:8000/api/jobs

# Should return: []
```

---

## Troubleshooting

### "Connection refused" on port 8000
- API server not running
- Solution: Run `python main.py --api`

### "Cannot connect to Docker daemon"
- Docker Desktop not running
- Solution: Start Docker Desktop, wait 30 seconds, then try again

### "Database connection failed"
- Postgres not running
- Solution: Run `docker-compose up -d postgres redis elasticsearch`

### Still getting 404 errors
- API server not started properly
- Check that you see "Application startup complete" in the terminal
- Try restarting: Press Ctrl+C, then run `python main.py --api` again

---

## What Works Now

✅ `GET /api/jobs` - List jobs  
✅ `POST /api/scrape` - Submit scraping job  
✅ `GET /api/status/{job_id}` - Check job status  
✅ `GET /api/preview/{job_id}` - Preview data  
✅ `GET /api/download/{job_id}?format=csv` - Download results  
✅ Dashboard UI at http://localhost:8000  

---

## Command Reference

### Start API
```bash
python main.py --api                    # Default port 8000
python main.py --api --api-port 9000   # Custom port
```

### Check Infrastructure
```bash
docker-compose ps
```

### Stop Everything
```bash
docker-compose down
```

### View Logs
Keep the API terminal open to see real-time logs.

---

## For Future Use

Remember the complete flow:

1. **Terminal 1** - Start infrastructure:
   ```bash
   docker-compose up -d postgres redis elasticsearch
   ```

2. **Terminal 2** - Start API server:
   ```bash
   python main.py --api
   ```

3. **Browser** - Go to:
   ```
   http://localhost:8000
   ```

That's it! You're ready to scrape.

---

## What Changed

- **main.py** now supports `--api` flag to start FastAPI server
- **run_api.bat** created for one-click startup (Windows)
- API endpoints are working and properly registered
- All 4 new export endpoints are available

No code changes to API endpoints were needed - they were always there, just not exposed with the right startup method!
