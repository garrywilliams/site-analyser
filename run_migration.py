#!/usr/bin/env python3
"""Run database migrations."""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = structlog.get_logger()

async def run_migration(migration_file: Path):
    """Run a specific migration file."""
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'database': os.getenv('DB_NAME', 'site_analysis'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', ''),
    }
    
    if not migration_file.exists():
        logger.error("migration_file_not_found", path=str(migration_file))
        return False
    
    try:
        # Connect to database
        conn = await asyncpg.connect(**db_config)
        logger.info("database_connected", host=db_config['host'], database=db_config['database'])
        
        # Read migration SQL
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        # Execute migration
        logger.info("running_migration", file=migration_file.name)
        await conn.execute(migration_sql)
        
        logger.info("migration_completed", file=migration_file.name)
        return True
        
    except Exception as e:
        logger.error("migration_failed", file=migration_file.name, error=str(e))
        return False
        
    finally:
        if 'conn' in locals():
            await conn.close()

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Run database migrations')
    parser.add_argument('migration_file', type=Path, nargs='?',
                        help='Path to migration SQL file')
    parser.add_argument('--list', action='store_true',
                        help='List available migrations')
    
    args = parser.parse_args()
    
    # Set up logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    migrations_dir = Path(__file__).parent / 'database' / 'migrations'
    
    if args.list:
        if migrations_dir.exists():
            migrations = sorted(migrations_dir.glob('*.sql'))
            print("📁 Available migrations:")
            for migration in migrations:
                print(f"   • {migration.name}")
        else:
            print("📭 No migrations directory found")
        return 0
    
    if not args.migration_file:
        # Default to the is_active migration
        args.migration_file = migrations_dir / '001_add_is_active_column.sql'
    
    if not args.migration_file.is_absolute():
        # Try relative to migrations directory
        potential_path = migrations_dir / args.migration_file
        if potential_path.exists():
            args.migration_file = potential_path
    
    success = await run_migration(args.migration_file)
    return 0 if success else 1

if __name__ == "__main__":
    exit(asyncio.run(main()))