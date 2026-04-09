# Data Export & Preview Features

## Overview
The scraper now provides comprehensive data viewing, downloading, and format conversion capabilities. After a scraping job completes, users can preview data, download in multiple formats, and convert between formats.

## Features Implemented

### 1. **Data Preview** 
- View scraped data directly in the browser
- Modal with paginated data table preview (up to 500 rows)
- Shows column headers and data samples
- Accessible via "PREVIEW" button in the dashboard

**Endpoint:** `GET /api/preview/{job_id}?limit=50`

Example:
```bash
curl http://localhost:8000/api/preview/abc-123-def?limit=100
```

Response:
```json
{
  "columns": ["name", "price", "currency", "rating", "url"],
  "row_count": 50,
  "total_columns": 5,
  "data": [
    {"name": "Product A", "price": "99.99", "currency": "INR", "rating": "4.5", "url": "..."},
    ...
  ],
  "job_id": "abc-123-def",
  "site_type": "product"
}
```

---

### 2. **Multi-Format Download**
Download scraped data in any of these formats:
- **CSV** - Comma-separated values (best for spreadsheets)
- **JSON** - Standard JSON objects (for APIs)
- **JSONL** - Line-delimited JSON (streaming-friendly)
- **XLSX** - Excel workbooks (formatted spreadsheets)
- **Parquet** - Apache Parquet (big data processing)

**Endpoint:** `GET /api/download/{job_id}?format=csv|json|jsonl|xlsx|parquet`

Example:
```bash
# Download as CSV
curl http://localhost:8000/api/download/abc-123-def?format=csv -o results.csv

# Download as JSON
curl http://localhost:8000/api/download/abc-123-def?format=json -o results.json

# Download as Excel
curl http://localhost:8000/api/download/abc-123-def?format=xlsx -o results.xlsx
```

---

### 3. **Format Conversion**
Convert existing output files between any supported formats.

**Endpoint:** `GET /api/export/{job_id}?target_format=csv|json|jsonl|xlsx|parquet`

Example:
```bash
# Convert original CSV output to JSON
curl http://localhost:8000/api/export/abc-123-def?target_format=json -o converted.json
```

---

### 4. **Available Formats API**
Get metadata about available formats for a completed job.

**Endpoint:** `GET /api/formats/{job_id}`

Response:
```json
{
  "job_id": "abc-123-def",
  "available_formats": ["csv", "json", "jsonl", "xlsx", "parquet"],
  "output_path": "data/output/scrape_session_20260401_120000.csv",
  "total_records": 150,
  "site_type": "product"
}
```

---

## Dashboard Enhancements

### Completed Job Actions
For each completed job, the dashboard now shows:

1. **PREVIEW Button** - Click to view data in modal
   - Shows table with up to 100 rows
   - Column headers and data samples
   - Scrollable table view

2. **DOWNLOAD Dropdown Menu** - Click to select format
   - CSV
   - JSON
   - JSONL
   - XLSX
   - Parquet
   - Auto-converts if original format differs

### Status Indicators
- **Processing** - Shows "Processing..." status
- **Completed** - Shows Preview + Download buttons
- **Failed** - Shows error message

---

## E-Commerce Data Standardization

For e-commerce/product websites, exported CSV files use standardized columns:

```csv
name,price,currency,rating,reviews_count,availability,url,source,scraped_at
```

Example output:
```csv
MacBook Pro 16",₹1,39,999,INR,4.5,2450,In Stock,https://amazon.in/dp/xyz,amazon,2026-04-01T14:30:00
```

---

## Data Converter Utilities

New module: `utils/data_converter.py`

Key functions:

### `DataConverter.csv_to_json(csv_path: str)`
Convert CSV file to JSON list of dictionaries

### `DataConverter.json_to_csv(json_data: List[Dict])`
Convert JSON data to CSV string

### `DataConverter.jsonl_to_json(jsonl_path: str)`
Convert JSONL file to JSON list

### `DataConverter.export_to_format(source_path, target_format, output_path)`
Universal converter between all supported formats

### `DataConverter.get_csv_preview(csv_path, limit=50)`
Get metadata and preview of CSV data

### `DataConverter.csv_to_csv_formatted(csv_path, site_type='product')`
Normalize CSV columns for e-commerce products

---

## API Job Workflow

1. **Submit Job**
   ```bash
   POST /api/scrape
   {
     "url": "https://amazon.in/s?k=laptop",
     "query": "laptops under 1 lakh",
     "pages": 5,
     "format": "csv"
   }
   
   Response: {"job_id": "abc-123-def"}
   ```

2. **Check Status**
   ```bash
   GET /api/status/abc-123-def
   ```

3. **Preview Data** (when completed)
   ```bash
   GET /api/preview/abc-123-def
   ```

4. **Download** (when completed)
   ```bash
   GET /api/download/abc-123-def?format=csv
   GET /api/download/abc-123-def?format=json
   ```

---

## Technical Details

### Supported Conversions
- CSV ↔ JSON
- CSV ↔ JSONL
- CSV ↔ XLSX
- CSV ↔ Parquet
- JSON ↔ JSONL
- JSON ↔ XLSX
- JSON ↔ Parquet
- All combinations via pandas

### Performance
- Preview: Up to 500 rows in memory
- Export: Streaming for large files
- Conversion: Memory-efficient using pandas chunks

### File Naming
Downloaded files are named:
- `{job_id}_{site_type}.{format}`
- Example: `abc-123-def_product.csv`

### Conversion Caching
- Converted files stored in same directory as original
- Pattern: `{original_name}_converted.{format}`
- Example: `scrape_session_20260401_120000_converted.json`

---

## Usage Examples

### Download as CSV from Python
```python
import requests

job_id = "abc-123-def"
response = requests.get(
    f"http://localhost:8000/api/download/{job_id}",
    params={"format": "csv"}
)

with open("results.csv", "wb") as f:
    f.write(response.content)
```

### Get preview
```python
response = requests.get(
    f"http://localhost:8000/api/preview/{job_id}",
    params={"limit": 50}
)
data = response.json()
print(f"Found {data['row_count']} records")
print(f"Columns: {data['columns']}")
```

### Convert format
```python
response = requests.get(
    f"http://localhost:8000/api/export/{job_id}",
    params={"target_format": "json"}
)

with open("results.json", "wb") as f:
    f.write(response.content)
```

---

## Error Handling

All endpoints return appropriate HTTP status codes:

- `200 OK` - Successful request
- `400 Bad Request` - Invalid format or job not ready
- `404 Not Found` - Job ID or file not found
- `500 Internal Server Error` - Conversion or processing failed

Error response:
```json
{
  "detail": "Data not ready. Job must be completed first."
}
```

---

## Future Enhancements

1. **Persistent Job Storage** - Store jobs in PostgreSQL instead of memory
2. **Partial Downloads** - Download specific columns or rows
3. **Scheduled Exports** - Auto-export on completion
4. **Data Filtering** - Filter/search before download
5. **Bulk Operations** - Export multiple jobs at once
6. **Webhooks** - Notify when job completes
