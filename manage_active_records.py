#!/usr/bin/env python3
"""Utility to manage is_active status for selective Agno agent processing."""

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional

import asyncpg
import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = structlog.get_logger()

class ActiveRecordManager:
    """Manages is_active status for selective processing."""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'database': os.getenv('DB_NAME', 'site_analysis'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', ''),
        }
        
    async def create_connection(self) -> asyncpg.Connection:
        """Create database connection."""
        try:
            conn = await asyncpg.connect(**self.db_config)
            return conn
        except Exception as e:
            logger.error("database_connection_failed", error=str(e))
            raise
    
    async def list_records(self, job_id: Optional[str] = None, active_only: bool = False) -> List[dict]:
        """List records with their active status."""
        conn = await self.create_connection()
        
        try:
            query = """
                SELECT id, job_id, company_name, original_url, domain,
                       analysis_status, is_active, processed_at::date
                FROM site_analysis_data
            """
            params = []
            
            conditions = []
            if job_id:
                conditions.append("job_id = $1")
                params.append(job_id)
            
            if active_only:
                param_num = len(params) + 1
                conditions.append(f"is_active = ${param_num}")
                params.append(True)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY company_name, original_url"
            
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
            
        finally:
            await conn.close()
    
    async def set_active_status(self, record_ids: List[int], is_active: bool) -> int:
        """Set is_active status for specific records."""
        if not record_ids:
            return 0
            
        conn = await self.create_connection()
        
        try:
            query = """
                UPDATE site_analysis_data 
                SET is_active = $1, processed_at = NOW()
                WHERE id = ANY($2)
            """
            
            result = await conn.execute(query, is_active, record_ids)
            count = int(result.split()[-1])  # Extract count from "UPDATE 5"
            
            status = "activated" if is_active else "deactivated"
            logger.info(f"records_{status}", count=count, record_ids=record_ids)
            return count
            
        finally:
            await conn.close()
    
    async def set_active_by_domain(self, domains: List[str], is_active: bool) -> int:
        """Set is_active status for records matching domain patterns."""
        if not domains:
            return 0
            
        conn = await self.create_connection()
        
        try:
            # Build OR conditions for domain matching
            conditions = []
            params = [is_active]
            
            for i, domain in enumerate(domains, 2):
                conditions.append(f"domain ILIKE ${i}")
                params.append(f"%{domain}%")
            
            query = f"""
                UPDATE site_analysis_data 
                SET is_active = $1, processed_at = NOW()
                WHERE {' OR '.join(conditions)}
            """
            
            result = await conn.execute(query, *params)
            count = int(result.split()[-1])
            
            status = "activated" if is_active else "deactivated"
            logger.info(f"records_{status}_by_domain", count=count, domains=domains)
            return count
            
        finally:
            await conn.close()
    
    async def reset_all_active(self, job_id: Optional[str] = None) -> int:
        """Reset all records to active=true for a fresh start."""
        conn = await self.create_connection()
        
        try:
            if job_id:
                query = """
                    UPDATE site_analysis_data 
                    SET is_active = true, processed_at = NOW()
                    WHERE job_id = $1
                """
                result = await conn.execute(query, job_id)
            else:
                query = """
                    UPDATE site_analysis_data 
                    SET is_active = true, processed_at = NOW()
                """
                result = await conn.execute(query)
            
            count = int(result.split()[-1])
            logger.info("all_records_activated", count=count, job_id=job_id)
            return count
            
        finally:
            await conn.close()
    
    async def get_active_summary(self) -> dict:
        """Get summary statistics of active vs inactive records."""
        conn = await self.create_connection()
        
        try:
            query = """
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE is_active = true) as active_records,
                    COUNT(*) FILTER (WHERE is_active = false) as inactive_records,
                    COUNT(*) FILTER (WHERE is_active = true AND analysis_status = 'pending') as active_pending,
                    COUNT(DISTINCT job_id) as total_jobs
                FROM site_analysis_data
            """
            
            row = await conn.fetchrow(query)
            return dict(row)
            
        finally:
            await conn.close()

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Manage is_active status for selective Agno processing')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List records with their active status')
    list_parser.add_argument('--job-id', help='Filter by job ID')
    list_parser.add_argument('--active-only', action='store_true', help='Show only active records')
    list_parser.add_argument('--limit', type=int, default=50, help='Limit number of results')
    
    # Activate command
    activate_parser = subparsers.add_parser('activate', help='Activate records')
    activate_parser.add_argument('--ids', nargs='+', type=int, help='Record IDs to activate')
    activate_parser.add_argument('--domains', nargs='+', help='Domain patterns to activate')
    activate_parser.add_argument('--all', action='store_true', help='Activate all records')
    activate_parser.add_argument('--job-id', help='Activate all records for specific job ID')
    
    # Deactivate command
    deactivate_parser = subparsers.add_parser('deactivate', help='Deactivate records')
    deactivate_parser.add_argument('--ids', nargs='+', type=int, help='Record IDs to deactivate')
    deactivate_parser.add_argument('--domains', nargs='+', help='Domain patterns to deactivate')
    
    # Summary command
    subparsers.add_parser('summary', help='Show summary of active/inactive records')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
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
    
    manager = ActiveRecordManager()
    
    try:
        if args.command == 'list':
            records = await manager.list_records(
                job_id=args.job_id,
                active_only=args.active_only
            )
            
            if not records:
                print("📭 No records found matching criteria")
                return 0
            
            print(f"📊 Found {len(records)} records:")
            print("=" * 100)
            print(f"{'ID':<6} {'Active':<8} {'Status':<12} {'Company':<30} {'Domain':<25} {'Date'}")
            print("-" * 100)
            
            for record in records[:args.limit]:
                active_icon = "✅" if record['is_active'] else "❌"
                print(f"{record['id']:<6} {active_icon:<8} {record['analysis_status']:<12} "
                      f"{record['company_name'][:29]:<30} {record['domain'][:24]:<25} {record['processed_at']}")
            
            if len(records) > args.limit:
                print(f"... and {len(records) - args.limit} more records")
        
        elif args.command == 'activate':
            count = 0
            
            if args.ids:
                count = await manager.set_active_status(args.ids, True)
                print(f"✅ Activated {count} records by ID")
                
            elif args.domains:
                count = await manager.set_active_by_domain(args.domains, True)
                print(f"✅ Activated {count} records matching domains: {', '.join(args.domains)}")
                
            elif args.all or args.job_id:
                count = await manager.reset_all_active(args.job_id)
                scope = f"for job {args.job_id}" if args.job_id else "globally"
                print(f"✅ Activated {count} records {scope}")
                
            else:
                print("❌ Must specify --ids, --domains, --all, or --job-id")
                return 1
        
        elif args.command == 'deactivate':
            count = 0
            
            if args.ids:
                count = await manager.set_active_status(args.ids, False)
                print(f"❌ Deactivated {count} records by ID")
                
            elif args.domains:
                count = await manager.set_active_by_domain(args.domains, False)
                print(f"❌ Deactivated {count} records matching domains: {', '.join(args.domains)}")
                
            else:
                print("❌ Must specify --ids or --domains")
                return 1
        
        elif args.command == 'summary':
            summary = await manager.get_active_summary()
            
            print("📊 Active Records Summary:")
            print("=" * 40)
            print(f"Total Records:     {summary['total_records']:,}")
            print(f"Active Records:    {summary['active_records']:,}")
            print(f"Inactive Records:  {summary['inactive_records']:,}")
            print(f"Active & Pending:  {summary['active_pending']:,}")
            print(f"Total Jobs:        {summary['total_jobs']:,}")
            
            if summary['total_records'] > 0:
                active_pct = (summary['active_records'] / summary['total_records']) * 100
                print(f"Active Percentage: {active_pct:.1f}%")
        
        return 0
        
    except Exception as e:
        logger.error("command_failed", command=args.command, error=str(e))
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))