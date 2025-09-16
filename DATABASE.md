# Database Loading Guide

This guide explains how to load scraped website data into PostgreSQL for analysis.

## Setup

1. **Install dependencies:**
   ```bash
   uv sync  # Includes asyncpg and beautifulsoup4
   ```

2. **Configure environment variables in `.env`:**
   ```bash
   cp env.example .env
   # Edit .env with your PostgreSQL connection details
   ```

3. **Create PostgreSQL database:**
   ```sql
   CREATE DATABASE site_analysis;
   ```

4. **Create database schema:**
   ```bash
   python load_to_database.py --results-file your_results.json --create-schema
   ```

## Usage

### Basic Usage
Load screenshot results into database:
```bash
python load_to_database.py --results-file test-job-id/screenshot_results.json
```

### With Company Mapping
If you have a company mapping file from the original HMRC scraper:
```bash
python load_to_database.py \
  --results-file test-job-id/screenshot_results.json \
  --company-mapping hmrc-software-urls.txt
```

### Create Schema and Load Data
```bash
python load_to_database.py \
  --results-file test-job-id/screenshot_results.json \
  --create-schema
```

## Database Schema

The `site_analysis_data` table contains:

### Core Fields
- `job_id` (UUID) - Links all resources from same scraping run
- `original_url` - URL as provided to scraper
- `final_url` - URL after following redirects  
- `company_name` - Extracted from HTML or mapping file
- `domain` - Parsed domain name

### Content Data
- `html_content` (TEXT) - Full HTML content
- `screenshot_image` (BYTEA) - Binary image data
- `screenshot_hash` - SHA-256 hash of image for deduplication

### Metadata
- `load_time_ms` - Page load time
- `viewport_size` - Screenshot dimensions (e.g., "1920x1080")
- `analysis_status` - pending/in_progress/completed/failed
- `processed_at` - When record was inserted

## Company Name Extraction

The loader tries multiple methods to get company names:

1. **Company mapping file** (if provided) - from original HMRC scraper
2. **HTML meta tags** - `og:site_name`, `title`, `h1`  
3. **Domain fallback** - parsed from URL

## Query Examples

```sql
-- View all pending records for a job
SELECT job_id, company_name, original_url, analysis_status 
FROM site_analysis_data 
WHERE job_id = 'your-job-id' AND analysis_status = 'pending';

-- Find duplicate images by hash
SELECT screenshot_hash, COUNT(*), array_agg(company_name)
FROM site_analysis_data 
GROUP BY screenshot_hash 
HAVING COUNT(*) > 1;

-- Get records with redirects
SELECT company_name, original_url, final_url 
FROM site_analysis_data 
WHERE redirected = true;
```

## Processing Pipeline

After loading data:
1. Records start with `analysis_status = 'pending'`
2. Update status to `in_progress` when processing with Agno agents
3. Update to `completed` when analysis is done
4. Store analysis results in separate related tables

## Error Handling

- Duplicate job_id + original_url combinations are updated (not inserted)
- Missing screenshot files are logged and skipped
- HTML extraction failures fall back to domain-based company names
- Database transaction ensures consistency