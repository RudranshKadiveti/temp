# API Endpoints Reference

## Base URL
```
http://localhost:8000
```

---

## 1. Submit Scraping Job

### Request
```
POST /api/scrape
Content-Type: application/json

{
  "url": "https://amazon.in/s?k=macbook",
  "query": "macbook pro m3",
  "pages": 5,
  "format": "csv",
  "min_price": "50000",
  "max_price": "150000",
  "brand": "apple",
  "min_rating": "4.0",
  "headless": true,
  "debug_snapshots": false
}
```

### Response
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Status Code
- `200 OK` - Job submitted successfully

---

## 2. Get Job Status

### Request
```
GET /api/status/{job_id}
```

### Response
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://amazon.in/s?k=macbook",
  "query": "macbook pro m3",
  "status": "completed",
  "total_records": 42,
  "pages_visited": 5,
  "apis_found": 2,
  "metrics": {
    "records_per_sec": 8.5,
    "llm_calls": 3,
    "total_time_seconds": 4.9
  },
  "site_type": "product",
  "output_path": "data/output/scrape_session_20260401_120000.csv",
  "created_at": "14:30:00",
  "completed_at": "14:35:00"
}
```

### Status Values
- `queued` - Waiting to start
- `processing` - Currently running
- `completed` - Successfully finished
- `failed` - Encountered an error

### Status Code
- `200 OK` - Job found
- `404 Not Found` - Job ID doesn't exist

---

## 3. List Recent Jobs

### Request
```
GET /api/jobs
```

### Response
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "url": "https://amazon.in/s?k=macbook",
    "query": "macbook pro",
    "status": "completed",
    "total_records": 42,
    "created_at": "14:30:00"
  },
  {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "url": "https://flipkart.com/search?q=laptop",
    "query": "gaming laptops",
    "status": "processing",
    "total_records": 15,
    "created_at": "14:25:00"
  }
]
```

### Notes
- Returns up to 50 most recent jobs
- Sorted by creation time (newest first)

### Status Code
- `200 OK` - Success

---

## 4. Download Data

### Request
```
GET /api/download/{job_id}?format={format}
```

### Parameters
| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| format | string | csv | csv, json, jsonl, xlsx, parquet |

### Examples
```bash
# Download as CSV
GET /api/download/550e8400-e29b-41d4-a716-446655440000?format=csv

# Download as JSON
GET /api/download/550e8400-e29b-41d4-a716-446655440000?format=json

# Download as Excel
GET /api/download/550e8400-e29b-41d4-a716-446655440000?format=xlsx

# Download as Parquet (big data)
GET /api/download/550e8400-e29b-41d4-a716-446655440000?format=parquet
```

### Response
- Binary file download
- Filename: `{job_id}_{site_type}.{format}`
- Example: `550e8400_product.csv`

### File Formats

**CSV** - Best for spreadsheets
```csv
name,price,currency,rating,reviews_count,availability,url,source,scraped_at
MacBook Pro 16",139999,INR,4.5,2450,In Stock,https://amazon.in/dp/xyz,amazon,2026-04-01T14:30:00Z
```

**JSON** - For APIs and web apps
```json
[
  {
    "name": "MacBook Pro 16\"",
    "price": "139999",
    "currency": "INR",
    "rating": "4.5",
    "reviews_count": "2450",
    "availability": "In Stock",
    "url": "https://amazon.in/dp/xyz",
    "source": "amazon",
    "scraped_at": "2026-04-01T14:30:00Z"
  }
]
```

**JSONL** - Line-delimited JSON (streaming)
```jsonl
{"name":"MacBook Pro 16\"","price":"139999",...}
{"name":"MacBook Pro 15\"","price":"109999",...}
```

**XLSX** - Excel workbook (formatted)
- Native Excel format with headers
- Compatible with Office, Google Sheets

**Parquet** - Big data format
- Highly compressed
- Best for Hadoop/Spark/Pandas

### Status Code
- `200 OK` - File ready
- `400 Bad Request` - Invalid format or job not ready
- `404 Not Found` - Job or file not found
- `500 Internal Error` - Conversion failed

---

## 5. Preview Data

### Request
```
GET /api/preview/{job_id}?limit={limit}
```

### Parameters
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| limit | integer | 50 | 1-500 |

### Response
```json
{
  "columns": ["name", "price", "currency", "rating", "reviews_count", "availability", "url", "source", "scraped_at"],
  "row_count": 50,
  "total_columns": 9,
  "data": [
    {
      "name": "MacBook Pro 16\"",
      "price": "139999",
      "currency": "INR",
      "rating": "4.5",
      "reviews_count": "2450",
      "availability": "In Stock",
      "url": "https://amazon.in/dp/xyz",
      "source": "amazon",
      "scraped_at": "2026-04-01T14:30:00Z"
    }
  ],
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "site_type": "product"
}
```

### Status Code
- `200 OK` - Preview available
- `400 Bad Request` - Job not completed
- `404 Not Found` - Job not found
- `500 Internal Error` - Preview generation failed

---

## 6. Export to Different Format

### Request
```
GET /api/export/{job_id}?target_format={format}
```

### Parameters
| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| target_format | string | json | csv, json, jsonl, xlsx, parquet |

### Examples
```bash
# Convert CSV output to JSON
GET /api/export/550e8400-e29b-41d4-a716-446655440000?target_format=json

# Convert to Parquet
GET /api/export/550e8400-e29b-41d4-a716-446655440000?target_format=parquet

# Convert to Excel
GET /api/export/550e8400-e29b-41d4-a716-446655440000?target_format=xlsx
```

### Response
- Binary file download
- Filename: `{job_id}_{site_type}.{target_format}`

### Status Code
- `200 OK` - Conversion successful
- `400 Bad Request` - Invalid format
- `404 Not Found` - Job not found
- `500 Internal Error` - Conversion failed

---

## 7. Get Available Formats

### Request
```
GET /api/formats/{job_id}
```

### Response
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "available_formats": ["csv", "json", "jsonl", "xlsx", "parquet"],
  "output_path": "data/output/scrape_session_20260401_120000.csv",
  "total_records": 42,
  "site_type": "product"
}
```

### Status Code
- `200 OK` - Metadata available
- `400 Bad Request` - Job not completed
- `404 Not Found` - Job not found

---

## 8. Get Dashboard

### Request
```
GET /
```

### Response
- HTML page (dashboard UI)
- Interactive form for submitting jobs
- Job list with status tracking
- Preview and download buttons

### Status Code
- `200 OK` - Dashboard loaded

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Data not ready. Job must be completed first."
}
```

### 404 Not Found
```json
{
  "detail": "Job not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Preview failed: [error details]"
}
```

---

## cURL Examples

### Submit job
```bash
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://amazon.in/s?k=laptop",
    "query": "gaming laptops under 100000",
    "pages": 3,
    "format": "csv"
  }'
```

### Get status
```bash
curl http://localhost:8000/api/status/550e8400-e29b-41d4-a716-446655440000
```

### Download CSV
```bash
curl http://localhost:8000/api/download/550e8400-e29b-41d4-a716-446655440000?format=csv \
  -o results.csv
```

### Download JSON
```bash
curl http://localhost:8000/api/download/550e8400-e29b-41d4-a716-446655440000?format=json \
  -o results.json > results.json
```

### Preview data
```bash
curl http://localhost:8000/api/preview/550e8400-e29b-41d4-a716-446655440000?limit=100 | jq
```

### Convert to Excel
```bash
curl http://localhost:8000/api/export/550e8400-e29b-41d4-a716-446655440000?target_format=xlsx \
  -o results.xlsx
```

---

## Python Requests Examples

### Submit job
```python
import requests

response = requests.post('http://localhost:8000/api/scrape', json={
    'url': 'https://amazon.in/s?k=laptop',
    'query': 'gaming laptops',
    'pages': 5,
    'format': 'csv'
})
job_id = response.json()['job_id']
```

### Check status
```python
status = requests.get(f'http://localhost:8000/api/status/{job_id}').json()
print(f"Status: {status['status']}, Records: {status['total_records']}")
```

### Download as JSON
```python
response = requests.get(
    f'http://localhost:8000/api/download/{job_id}?format=json'
)
with open('results.json', 'wb') as f:
    f.write(response.content)
```

### Get preview
```python
preview = requests.get(
    f'http://localhost:8000/api/preview/{job_id}?limit=50'
).json()

print(f"Columns: {preview['columns']}")
print(f"Records: {preview['row_count']}")
for row in preview['data']:
    print(row)
```

---

## Rate Limiting

Currently no rate limiting implemented. Future updates may include:
- 100 requests/minute per IP
- Prioritize completed jobs over new submissions
- Job queue limits

---

## Authentication

Currently no authentication required. Future security features:
- API key authentication
- User-based job isolation
- Role-based access control

---

## Pagination

For list endpoints:
- `GET /api/jobs` returns up to 50 recent jobs
- Sorted by creation time (newest first)
- No pagination parameters currently supported
