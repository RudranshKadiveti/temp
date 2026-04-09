# Quick Start: Data Export & Download Features

## Running the Scraper

```bash
# Start infrastructure (if not already running)
docker-compose up -d postgres redis elasticsearch

# Start the API
python main.py

# The dashboard will be available at: http://localhost:8000
```

## Using the Dashboard

### 1. **Submit a Scraping Job**
- Enter target URL (e.g., `https://amazon.in/s?k=macbook`)
- Optional: Add extraction strategy/query (e.g., "find all macbook pro variants")
- Set max pages (default: 5)
- Choose output format (CSV recommended for e-commerce)
- Click "INITIALIZE EXTRACTION"

### 2. **Monitor Job Progress**
- Jobs appear in the table below
- Status shows: queued → processing → completed (or failed)
- Total records counter updates in real-time
- Auto-refresh every 5 seconds

### 3. **View Data (Preview)**
- When job completes, click **PREVIEW** button
- Modal opens showing data in table format
- See column headers and sample rows (up to 100)
- Scrollable preview for browsing data

### 4. **Download Data**
- Click **DOWNLOAD ▼** dropdown for completed jobs
- Select desired format:
  - **CSV** - Best for spreadsheets (Excel, Google Sheets)
  - **JSON** - For APIs and web apps
  - **JSONL** - For streaming/big data tools
  - **XLSX** - Native Excel format
  - **Parquet** - For Hadoop/Spark processing
- File downloads automatically

---

## Command-Line Usage (cURL)

### Submit a scraping job
```bash
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://amazon.in/s?k=laptop",
    "query": "gaming laptops",
    "pages": 3,
    "format": "csv"
  }'

# Response: {"job_id": "abc-123-def"}
```

### Check job status
```bash
curl http://localhost:8000/api/status/abc-123-def
```

### Get data preview
```bash
curl http://localhost:8000/api/preview/abc-123-def?limit=50
```

### Download as CSV
```bash
curl http://localhost:8000/api/download/abc-123-def?format=csv -o data.csv
```

### Download as JSON
```bash
curl http://localhost:8000/api/download/abc-123-def?format=json -o data.json
```

### Convert to Excel
```bash
curl http://localhost:8000/api/download/abc-123-def?format=xlsx -o results.xlsx
```

### Get available formats
```bash
curl http://localhost:8000/api/formats/abc-123-def
```

---

## Python Script Example

```python
import requests
import time

# 1. Submit job
response = requests.post('http://localhost:8000/api/scrape', json={
    'url': 'https://amazon.in/s?k=macbook',
    'query': 'macbook pro',
    'pages': 5,
    'format': 'csv'
})

job_id = response.json()['job_id']
print(f"Job submitted: {job_id}")

# 2. Wait for completion
while True:
    status = requests.get(f'http://localhost:8000/api/status/{job_id}').json()
    print(f"Status: {status['status']} - Records: {status['total_records']}")
    
    if status['status'] == 'completed':
        break
    elif status['status'] == 'failed':
        print(f"Job failed: {status['error']}")
        exit(1)
    
    time.sleep(5)

# 3. Download as JSON
response = requests.get(f'http://localhost:8000/api/download/{job_id}?format=json')
with open('results.json', 'wb') as f:
    f.write(response.content)

print("✓ Downloaded to results.json")

# 4. Get preview
preview = requests.get(f'http://localhost:8000/api/preview/{job_id}?limit=20').json()
print(f"\nPreview ({preview['row_count']} rows):")
print(f"Columns: {preview['columns']}")
for row in preview['data'][:3]:
    print(row)
```

---

## E-Commerce Data Format

For e-commerce websites, data is exported with these standard columns:

| Column | Description | Example |
|--------|-------------|---------|
| name | Product name | MacBook Pro 16" |
| price | Product price | 139999 |
| currency | Currency code | INR |
| rating | Star rating | 4.5 |
| reviews_count | Number of reviews | 2450 |
| availability | Stock status | In Stock |
| url | Product URL | https://amazon.in/dp/xyz |
| source | Website | amazon |
| scraped_at | Scrape timestamp | 2026-04-01T14:30:00Z |

**Example CSV row:**
```
MacBook Pro 16",139999,INR,4.5,2450,In Stock,https://amazon.in/dp/xyz,amazon,2026-04-01T14:30:00Z
```

---

## Troubleshooting

### "Data not ready" error
- Wait for job to complete (check status first)
- Job must be in "completed" state to download/preview

### "File not found" error
- Output file path may be incorrect
- Check that scraping completed successfully

### Conversion fails
- Original file may be corrupted
- Try downloading original format first

### Large file downloads take long
- For large datasets, use Parquet format (most efficient)
- Or download in chunks using limit parameter

---

## File Downloads Location

Downloaded files go to your browser's default download folder. Typical locations:
- **Windows**: `C:\Users\{username}\Downloads\`
- **Mac**: `/Users/{username}/Downloads/`
- **Linux**: `/home/{username}/Downloads/`

Files are named: `{job_id}_{site_type}.{format}`
- Example: `abc-123-def_product.csv`

---

## Data Storage

Scraped data is stored in multiple locations:

1. **Raw HTML**: `data/raw_html/` (hashed files)
2. **Structured Data**: `data/output/` (CSV/JSON/Excel files)
3. **Database**: PostgreSQL (metadata + structured records)
4. **Search Index**: Elasticsearch (full-text search)

---

## Notes

- Jobs are tracked in memory (lost on API restart)
- For persistence, store in PostgreSQL (future feature)
- Preview limited to 500 rows for performance
- Large datasets recommended in Parquet format
- All timestamps in UTC (ISO 8601 format)
