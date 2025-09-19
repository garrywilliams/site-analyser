#!/usr/bin/env python3
"""
Upload Preprocessing Results to PostgreSQL

Simplified script to import flattened preprocessing results into PostgreSQL database.
Uses environment variables for database configuration like load_to_database.py.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

import asyncpg
import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = structlog.get_logger()


class PreprocessingResultsUploader:
    """Uploads preprocessing results to PostgreSQL database."""
    
    # Define the flattened schema for PostgreSQL
    SCHEMA_COLUMNS = [
        ('job_id', 'TEXT'),
        ('original_url', 'TEXT'),
        ('final_url', 'TEXT'), 
        ('domain', 'TEXT'),
        ('company_name', 'TEXT'),
        ('html_path', 'TEXT'),
        ('html_size', 'INTEGER'),
        ('screenshot_path', 'TEXT'),
        ('screenshot_data', 'BYTEA'),
        ('screenshot_hash', 'TEXT'),
        ('load_time_ms', 'INTEGER'),
        ('viewport_size', 'TEXT'),
        ('redirected', 'BOOLEAN'),
        ('status', 'TEXT'),
        ('error_message', 'TEXT'),
        ('timestamp', 'TIMESTAMP'),
        # SSL info (flattened from ssl_info.*)
        ('ssl_has_ssl', 'BOOLEAN'),
        ('ssl_is_valid', 'BOOLEAN'),
        ('ssl_issuer', 'TEXT'),
        ('ssl_subject', 'TEXT'),
        ('ssl_expires_date', 'TIMESTAMP'),
        ('ssl_days_until_expiry', 'INTEGER'),
        ('ssl_certificate_error', 'TEXT'),
        # Bot protection (flattened from bot_protection.*)
        ('bot_detected', 'BOOLEAN'),
        ('bot_protection_type', 'TEXT'),
        ('bot_indicators', 'JSONB'),  # Store as JSONB for better querying
        ('bot_confidence', 'REAL'),
        # Processing workflow columns
        ('is_active', 'BOOLEAN'),
        ('analysis_status', 'TEXT'),
    ]
    
    def __init__(self, table_name: str = 'preprocessing_results', base_path: str = '.'):
        """Initialize uploader with database config from environment."""
        self.table_name = table_name
        self.base_path = Path(base_path)
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': os.getenv('POSTGRES_DB', 'site_analysis'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', ''),
        }
    
    async def create_connection(self) -> asyncpg.Connection:
        """Create database connection."""
        try:
            conn = await asyncpg.connect(**self.db_config)
            logger.info("database_connected", 
                       host=self.db_config['host'], 
                       database=self.db_config['database'])
            return conn
        except Exception as e:
            logger.error("database_connection_failed", error=str(e), config=self.db_config)
            raise
    
    def flatten_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten a single result from nested JSON to flat dictionary.
        
        Args:
            result: Single result from JSON results array
            
        Returns:
            Flattened dictionary ready for database insert
        """
        from datetime import datetime, timezone
        import json
        
        flattened = {}
        
        # Direct fields
        direct_fields = [
            'job_id', 'original_url', 'final_url', 'domain', 'company_name',
            'html_path', 'html_size', 'screenshot_path', 'screenshot_hash', 
            'load_time_ms', 'viewport_size', 'redirected', 'status', 
            'error_message'
        ]
        
        for field in direct_fields:
            flattened[field] = result.get(field)
        
        # Load screenshot data from file
        screenshot_path_str = result.get('screenshot_path')
        if screenshot_path_str:
            try:
                screenshot_path = Path(screenshot_path_str)
                if not screenshot_path.is_absolute():
                    screenshot_path = self.base_path / screenshot_path
                
                if screenshot_path.exists():
                    with open(screenshot_path, 'rb') as f:
                        flattened['screenshot_data'] = f.read()
                    logger.info("screenshot_loaded", path=str(screenshot_path), size=len(flattened['screenshot_data']))
                else:
                    logger.error("screenshot_not_found", path=str(screenshot_path), exists=screenshot_path.exists())
                    flattened['screenshot_data'] = None
            except Exception as e:
                logger.error("screenshot_load_failed", path=screenshot_path_str, error=str(e))
                flattened['screenshot_data'] = None
        else:
            logger.warning("no_screenshot_path", url=result.get('original_url'))
            flattened['screenshot_data'] = None
        
        # Handle timestamp conversion - convert to UTC and remove timezone info for PostgreSQL
        timestamp_str = result.get('timestamp')
        if timestamp_str:
            try:
                # Parse ISO format timestamp string to datetime object
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                # Convert to UTC and make naive (PostgreSQL TIMESTAMP without timezone)
                if dt.tzinfo is not None:
                    dt_utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    dt_utc = dt
                flattened['timestamp'] = dt_utc
                logger.debug("timestamp_parsed", original=timestamp_str, parsed=dt_utc)
            except (ValueError, AttributeError) as e:
                logger.error("timestamp_parse_failed", timestamp=timestamp_str, error=str(e))
                flattened['timestamp'] = None
        else:
            flattened['timestamp'] = None
        
        # SSL info (ssl_info.* -> ssl_*)
        ssl_info = result.get('ssl_info', {})
        flattened['ssl_has_ssl'] = ssl_info.get('has_ssl')
        flattened['ssl_is_valid'] = ssl_info.get('is_valid')
        flattened['ssl_issuer'] = ssl_info.get('issuer')
        flattened['ssl_subject'] = ssl_info.get('subject')
        flattened['ssl_days_until_expiry'] = ssl_info.get('days_until_expiry')
        flattened['ssl_certificate_error'] = ssl_info.get('certificate_error')
        
        # Handle SSL expires_date conversion - convert to UTC and remove timezone info
        ssl_expires_str = ssl_info.get('expires_date')
        if ssl_expires_str:
            try:
                dt = datetime.fromisoformat(ssl_expires_str.replace('Z', '+00:00'))
                # Convert to UTC and make naive (PostgreSQL TIMESTAMP without timezone)
                if dt.tzinfo is not None:
                    dt_utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    dt_utc = dt
                flattened['ssl_expires_date'] = dt_utc
                logger.debug("ssl_expires_parsed", original=ssl_expires_str, parsed=dt_utc)
            except (ValueError, AttributeError) as e:
                logger.error("ssl_expires_parse_failed", expires_date=ssl_expires_str, error=str(e))
                flattened['ssl_expires_date'] = None
        else:
            flattened['ssl_expires_date'] = None
        
        # Bot protection (bot_protection.* -> bot_*)
        bot_protection = result.get('bot_protection', {})
        flattened['bot_detected'] = bot_protection.get('detected')
        flattened['bot_protection_type'] = bot_protection.get('protection_type')
        flattened['bot_confidence'] = bot_protection.get('confidence')
        
        # Convert indicators list to JSON string for JSONB storage
        indicators = bot_protection.get('indicators', [])
        flattened['bot_indicators'] = json.dumps(indicators)
        
        # Set default workflow status for new records
        flattened['is_active'] = True
        flattened['analysis_status'] = 'pending'
        
        return flattened
    
    def generate_create_table_sql(self) -> str:
        """Generate CREATE TABLE SQL for PostgreSQL."""
        columns_sql = []
        for col_name, col_type in self.SCHEMA_COLUMNS:
            columns_sql.append(f"    {col_name} {col_type}")
        
        return f"""
CREATE TABLE IF NOT EXISTS {self.table_name} (
    id SERIAL PRIMARY KEY,
{','.join(columns_sql)},
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, original_url)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_{self.table_name}_domain ON {self.table_name}(domain);
CREATE INDEX IF NOT EXISTS idx_{self.table_name}_status ON {self.table_name}(status);
CREATE INDEX IF NOT EXISTS idx_{self.table_name}_ssl_valid ON {self.table_name}(ssl_is_valid);
CREATE INDEX IF NOT EXISTS idx_{self.table_name}_bot_detected ON {self.table_name}(bot_detected);
CREATE INDEX IF NOT EXISTS idx_{self.table_name}_job_id ON {self.table_name}(job_id);
"""
    
    def generate_insert_sql(self) -> str:
        """Generate INSERT SQL with ON CONFLICT handling."""
        columns = [col_name for col_name, _ in self.SCHEMA_COLUMNS]
        placeholders = ', '.join([f'${i+1}' for i in range(len(columns))])
        
        return f"""
INSERT INTO {self.table_name} ({', '.join(columns)})
VALUES ({placeholders})
ON CONFLICT (job_id, original_url) DO UPDATE SET
    final_url = EXCLUDED.final_url,
    status = EXCLUDED.status,
    load_time_ms = EXCLUDED.load_time_ms,
    ssl_is_valid = EXCLUDED.ssl_is_valid,
    bot_detected = EXCLUDED.bot_detected,
    created_at = CURRENT_TIMESTAMP
"""
    
    async def create_table(self, connection: asyncpg.Connection):
        """Create table and indexes."""
        create_sql = self.generate_create_table_sql()
        await connection.execute(create_sql)
        logger.info("table_created", table=self.table_name)
    
    async def upload_results(self, results: List[Dict[str, Any]]) -> int:
        """
        Upload results to PostgreSQL database.
        
        Args:
            results: List of result dictionaries from JSON
            
        Returns:
            Number of rows inserted/updated
        """
        connection = await self.create_connection()
        
        try:
            # Create table and indexes
            await self.create_table(connection)
            
            # Prepare data
            flattened_results = [self.flatten_result(result) for result in results]
            insert_sql = self.generate_insert_sql()
            
            # Batch insert with conflict handling
            rows_data = []
            for result in flattened_results:
                row = [result.get(col_name) for col_name, _ in self.SCHEMA_COLUMNS]
                rows_data.append(row)
                # Debug: log if screenshot_data is present
                if result.get('screenshot_data'):
                    logger.info("inserting_with_screenshot", url=result.get('original_url'), size=len(result.get('screenshot_data')))
                else:
                    logger.warning("no_screenshot_data_for_insert", url=result.get('original_url'))
            
            await connection.executemany(insert_sql, rows_data)
            
            logger.info("upload_completed", 
                       rows_processed=len(rows_data),
                       table=self.table_name)
            
            return len(rows_data)
            
        finally:
            await connection.close()


def load_results_from_json(json_file_path: Path) -> List[Dict[str, Any]]:
    """Load results from preprocessing JSON file."""
    try:
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        
        results = data.get('results', [])
        logger.info("json_loaded", 
                   file=str(json_file_path),
                   job_id=data.get('job_id'),
                   total_results=len(results))
        
        return results
        
    except FileNotFoundError:
        logger.error("json_file_not_found", file=str(json_file_path))
        raise
    except json.JSONDecodeError as e:
        logger.error("json_parse_error", file=str(json_file_path), error=str(e))
        raise


def preview_flattened_data(results: List[Dict[str, Any]], base_path: str = '.', limit: int = 3):
    """Preview what the flattened data will look like."""
    uploader = PreprocessingResultsUploader(base_path=base_path)
    
    print(f"\n📊 Preview of flattened data (showing first {min(limit, len(results))} results):\n")
    
    for i, result in enumerate(results[:limit]):
        flattened = uploader.flatten_result(result)
        
        print(f"Result {i+1}:")
        print(f"  📁 Job: {flattened['job_id']}")
        print(f"  🌐 URL: {flattened['original_url']} -> {flattened['final_url']}")
        print(f"  🏢 Company: {flattened['company_name']}")
        print(f"  ✅ Status: {flattened['status']}")
        print(f"  🔒 SSL: valid={flattened['ssl_is_valid']}, issuer={flattened['ssl_issuer']}, expires_in={flattened['ssl_days_until_expiry']} days")
        print(f"  🛡️ Bot Protection: detected={flattened['bot_detected']}, type={flattened['bot_protection_type']}")
        print(f"  ⚡ Performance: {flattened['load_time_ms']}ms")
        print()


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Upload preprocessing results to PostgreSQL database',
        epilog="""
Environment Variables Required:
  POSTGRES_HOST     - Database host (default: localhost)
  POSTGRES_PORT     - Database port (default: 5432)  
  POSTGRES_DB       - Database name (default: site_analysis)
  POSTGRES_USER     - Database user (default: postgres)
  POSTGRES_PASSWORD - Database password (required)

Example:
  python scripts/upload_preprocessing_results.py results.json --preview
  python scripts/upload_preprocessing_results.py results.json --table my_results
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('json_file', help='Path to JSON results file from preprocessing')
    parser.add_argument('--table', default='preprocessing_results', 
                       help='Table name (default: preprocessing_results)')
    parser.add_argument('--base-path', default='.', 
                       help='Base path for loading image files from relative paths')
    parser.add_argument('--preview', action='store_true', 
                       help='Preview flattened data without uploading')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show SQL schema without uploading')
    
    args = parser.parse_args()
    
    # Check required environment variables
    if not os.getenv('POSTGRES_PASSWORD') and not (args.preview and not args.dry_run):
        print("❌ Error: POSTGRES_PASSWORD environment variable is required")
        print("Set it in your .env file or environment")
        sys.exit(1)
    
    # Load results
    json_file_path = Path(args.json_file)
    if not json_file_path.exists():
        print(f"❌ Error: JSON file not found: {json_file_path}")
        sys.exit(1)
    
    results = load_results_from_json(json_file_path)
    
    if not results:
        print("⚠️  No results found in JSON file")
        sys.exit(0)
    
    print(f"📁 Loaded {len(results)} results from {json_file_path}")
    
    # Preview mode
    if args.preview:
        preview_flattened_data(results, args.base_path)
        return
    
    # Create uploader
    uploader = PreprocessingResultsUploader(args.table, args.base_path)
    
    # Dry run mode  
    if args.dry_run:
        print(f"\n🔍 DRY RUN - Database Configuration:")
        print(f"  Host: {uploader.db_config['host']}:{uploader.db_config['port']}")
        print(f"  Database: {uploader.db_config['database']}")
        print(f"  User: {uploader.db_config['user']}")
        print(f"  Table: {args.table}")
        print(f"\n📋 SQL Schema:")
        print(uploader.generate_create_table_sql())
        preview_flattened_data(results, args.base_path, limit=2)
        return
    
    # Actual upload
    try:
        rows_processed = await uploader.upload_results(results)
        print(f"✅ Successfully processed {rows_processed} results")
        print(f"📊 Data available in table: {args.table}")
        
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        logger.error("upload_failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())