"""
Data format conversion utilities for supporting multiple export formats.
"""
import json
import csv
import io
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd


class DataConverter:
    """Convert between CSV, JSON, and other formats."""

    @staticmethod
    def _normalize_format(fmt: str) -> str:
        value = (fmt or "").strip().lower()
        aliases = {
            "csv_file": "csv",
            "csvfile": "csv",
            "excel": "xlsx",
        }
        return aliases.get(value, value)
    
    @staticmethod
    def csv_to_json(csv_path: str) -> List[Dict[str, Any]]:
        """Convert CSV file to JSON format."""
        try:
            df = pd.read_csv(csv_path)
            return df.to_dict('records')
        except Exception as e:
            raise ValueError(f"Failed to read CSV: {e}")

    @staticmethod
    def _json_safe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Convert DataFrame rows to JSON-safe records (NaN/NaT -> None)."""
        safe_df = df.astype(object).where(pd.notna(df), None)
        return safe_df.to_dict('records')
    
    @staticmethod
    def json_to_csv(json_data: List[Dict[str, Any]]) -> str:
        """Convert JSON data to CSV format string."""
        if not json_data:
            return ""
        
        df = pd.DataFrame(json_data)
        return df.to_csv(index=False)
    
    @staticmethod
    def jsonl_to_json(jsonl_path: str) -> List[Dict[str, Any]]:
        """Convert JSONL (line-delimited JSON) file to JSON list."""
        records = []
        try:
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
        except Exception as e:
            raise ValueError(f"Failed to read JSONL: {e}")
        return records
    
    @staticmethod
    def jsonl_to_csv_file(jsonl_path: str, output_csv_path: str) -> None:
        """Convert JSONL to CSV file."""
        records = DataConverter.jsonl_to_json(jsonl_path)
        if records:
            df = pd.DataFrame(records)
            df.to_csv(output_csv_path, index=False)
    
    @staticmethod
    def csv_to_csv_formatted(csv_path: str, site_type: str = "product") -> str:
        """
        Ensure CSV has proper columns for e-commerce data.
        Standardizes column names and data formatting.
        """
        df = pd.read_csv(csv_path)
        
        # Standard e-commerce product columns
        standard_columns = {
            'product': ['name', 'price', 'currency', 'rating', 'reviews_count', 
                       'availability', 'url', 'source', 'scraped_at'],
            'article': ['title', 'author', 'publish_date', 'content', 'tags', 
                       'url', 'source', 'scraped_at'],
            'listing': ['title', 'url', 'source', 'scraped_at']
        }
        
        # Normalize columns
        columns_to_keep = []
        for col in standard_columns.get(site_type, standard_columns['product']):
            # Try exact match first, then case-insensitive
            if col in df.columns:
                columns_to_keep.append(col)
            else:
                for df_col in df.columns:
                    if df_col.lower() == col.lower():
                        df.rename(columns={df_col: col}, inplace=True)
                        columns_to_keep.append(col)
                        break
        
        # Keep only standard columns + any extra columns
        existing_cols = [c for c in columns_to_keep if c in df.columns]
        other_cols = [c for c in df.columns if c not in existing_cols]
        final_columns = existing_cols + other_cols
        
        df = df[final_columns]
        return df.to_csv(index=False)
    
    @staticmethod
    def get_csv_preview(csv_path: str, limit: int = 50) -> Dict[str, Any]:
        """Get preview of CSV data with metadata."""
        try:
            try:
                df = pd.read_csv(csv_path, nrows=limit, encoding="utf-8")
            except Exception:
                try:
                    # Fallback for malformed legacy CSV rows.
                    df = pd.read_csv(
                        csv_path,
                        nrows=limit,
                        engine="python",
                        on_bad_lines="skip",
                        encoding="utf-8",
                        encoding_errors="replace",
                    )
                except Exception:
                    # Final fallback using csv module; skips malformed lines deterministically.
                    rows: list[dict[str, Any]] = []
                    with open(csv_path, "r", encoding="utf-8", errors="replace", newline="") as handle:
                        reader = csv.reader(handle)
                        header = next(reader, [])
                        for row in reader:
                            if not header:
                                break
                            if len(row) != len(header):
                                continue
                            rows.append(dict(zip(header, row)))
                            if len(rows) >= limit:
                                break
                    df = pd.DataFrame(rows)
            return {
                "columns": list(df.columns),
                "row_count": len(df),
                "data": DataConverter._json_safe_records(df),
                "total_columns": len(df.columns)
            }
        except Exception as e:
            raise ValueError(f"Failed to preview CSV: {e}")
    
    @staticmethod
    def get_json_preview(json_path: str, limit: int = 50) -> Dict[str, Any]:
        """Get preview of JSON data with metadata."""
        try:
            path = Path(json_path)
            if path.suffix.lower() == ".jsonl":
                df = pd.read_json(path, lines=True, nrows=limit)
            else:
                df = pd.read_json(path)
                if len(df) > limit:
                    df = df.head(limit)
            return {
                "columns": list(df.columns),
                "row_count": len(df),
                "data": DataConverter._json_safe_records(df),
                "total_columns": len(df.columns)
            }
        except Exception as e:
            raise ValueError(f"Failed to preview JSON: {e}")
    
    @staticmethod
    def export_to_format(source_path: str, target_format: str, output_path: Optional[str] = None) -> str:
        """
        Export data to target format.
        Supported formats: csv, json, jsonl, xlsx
        """
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        source_format = DataConverter._normalize_format(source_path.suffix.lower().lstrip('.'))
        target_format = DataConverter._normalize_format(target_format)
        
        # Load data
        if source_format == 'csv':
            df = pd.read_csv(source_path)
        elif source_format in ['json', 'jsonl']:
            df = pd.read_json(source_path, lines=(source_format == 'jsonl'))
        elif source_format == 'xlsx':
            df = pd.read_excel(source_path)
        elif source_format == 'parquet':
            df = pd.read_parquet(source_path)
        else:
            raise ValueError(f"Unsupported source format: {source_format}")
        
        # Generate output path if not provided
        if output_path is None:
            base_name = source_path.stem
            output_path = source_path.parent / f"{base_name}.{target_format}"
        
        # Save in target format
        output_path = Path(output_path)
        if target_format == 'csv':
            df.to_csv(output_path, index=False)
        elif target_format in ['json', 'jsonl']:
            if target_format == 'jsonl':
                df.to_json(output_path, orient='records', lines=True, force_ascii=False)
            else:
                df.to_json(output_path, orient='records', force_ascii=False)
        elif target_format == 'xlsx':
            df.to_excel(output_path, index=False)
        elif target_format == 'parquet':
            df.to_parquet(output_path, index=False)
        else:
            raise ValueError(f"Unsupported target format: {target_format}")
        
        return str(output_path)
