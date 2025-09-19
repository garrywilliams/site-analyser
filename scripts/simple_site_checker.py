#!/usr/bin/env python3
"""
MTD Compliance Site Checker
Processes website screenshots for Making Tax Digital compliance using Agno agents.
"""

import asyncio
import base64
import csv
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import asyncpg
import structlog
from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.openai import OpenAILike

# Load environment variables
load_dotenv()

logger = structlog.get_logger()


class MTDDatabaseTools:
    """Database tools for MTD compliance checking."""

    def __init__(self, db_config: Dict[str, Any], source_table: str = "preprocessing_results"):
        self.db_config = db_config
        self.source_table = source_table

    async def create_connection(self) -> asyncpg.Connection:
        """Create database connection."""
        try:
            conn = await asyncpg.connect(**self.db_config)
            return conn
        except Exception as e:
            logger.error("database_connection_failed", error=str(e))
            raise

    async def ensure_tables_exist(self):
        """Create MTD tables if they don't exist."""
        conn = await self.create_connection()
        try:
            # Create normalized AC results table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mtd_ac_results (
                    id SERIAL PRIMARY KEY,
                    job_id VARCHAR(255) NOT NULL,
                    website_url TEXT NOT NULL,
                    ac_number INTEGER NOT NULL CHECK (ac_number >= 1 AND ac_number <= 10),
                    ac_result VARCHAR(20) NOT NULL,
                    ac_confidence VARCHAR(10),
                    ac_explanation TEXT,
                    analysis_timestamp TIMESTAMP DEFAULT NOW(),
                    ai_model_used VARCHAR(100),
                    created_date TIMESTAMP DEFAULT NOW(),
                    last_updated_date TIMESTAMP DEFAULT NOW(),
                    version_num INTEGER DEFAULT 1,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by VARCHAR(255) DEFAULT 'mtd_checker',
                    last_updated_by VARCHAR(255) DEFAULT 'mtd_checker',
                    remarks TEXT,
                    UNIQUE(job_id, website_url, ac_number)
                );
                
                CREATE INDEX IF NOT EXISTS idx_ac_results_job_id ON mtd_ac_results(job_id);
                CREATE INDEX IF NOT EXISTS idx_ac_results_url ON mtd_ac_results(website_url);
                CREATE INDEX IF NOT EXISTS idx_ac_results_ac_number ON mtd_ac_results(ac_number);
                CREATE INDEX IF NOT EXISTS idx_ac_results_result ON mtd_ac_results(ac_result);
            """
            )

            # Create summary results table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mtd_compliance_summary (
                    id SERIAL PRIMARY KEY,
                    job_id VARCHAR(255) NOT NULL,
                    website_url TEXT NOT NULL,
                    overall_status VARCHAR(20),
                    total_passed INTEGER DEFAULT 0,
                    total_failed INTEGER DEFAULT 0,
                    total_suspect INTEGER DEFAULT 0,
                    analysis_timestamp TIMESTAMP DEFAULT NOW(),
                    ai_model_used VARCHAR(100),
                    created_date TIMESTAMP DEFAULT NOW(),
                    last_updated_date TIMESTAMP DEFAULT NOW(),
                    version_num INTEGER DEFAULT 1,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by VARCHAR(255) DEFAULT 'mtd_checker',
                    last_updated_by VARCHAR(255) DEFAULT 'mtd_checker',
                    remarks TEXT,
                    UNIQUE(job_id, website_url)
                );
                
                CREATE INDEX IF NOT EXISTS idx_summary_job_id ON mtd_compliance_summary(job_id);
                CREATE INDEX IF NOT EXISTS idx_summary_url ON mtd_compliance_summary(website_url);
                CREATE INDEX IF NOT EXISTS idx_summary_status ON mtd_compliance_summary(overall_status);
            """
            )

            logger.info("mtd_tables_ensured")

        finally:
            await conn.close()

    async def fetch_image_from_db(self, job_id: str, website_url: str) -> Optional[bytes]:
        """Fetch screenshot image from source table."""
        conn = await self.create_connection()
        try:
            # Check if source table has screenshot_data column (BYTEA)
            result = await conn.fetchrow(
                f"""
                SELECT screenshot_data FROM {self.source_table} 
                WHERE job_id = $1 AND original_url = $2 AND is_active = TRUE
            """,
                job_id,
                website_url,
            )

            if result and result["screenshot_data"]:
                logger.info(
                    "image_fetched_from_db", job_id=job_id, url=website_url, table=self.source_table
                )
                return bytes(result["screenshot_data"])
            else:
                # Fallback: try to load from screenshot_path
                result = await conn.fetchrow(
                    f"""
                    SELECT screenshot_path FROM {self.source_table} 
                    WHERE job_id = $1 AND original_url = $2 AND is_active = TRUE
                """,
                    job_id,
                    website_url,
                )

                if result and result["screenshot_path"]:
                    screenshot_path = Path(result["screenshot_path"])
                    if screenshot_path.exists():
                        with open(screenshot_path, "rb") as f:
                            image_data = f.read()
                        logger.info(
                            "image_loaded_from_path",
                            job_id=job_id,
                            url=website_url,
                            path=str(screenshot_path),
                        )
                        return image_data

                logger.warning(
                    "image_not_found", job_id=job_id, url=website_url, table=self.source_table
                )
                return None

        finally:
            await conn.close()

    async def save_ac_results(
        self, job_id: str, website_url: str, results: Dict[str, Any], ai_model: str
    ):
        """Save individual AC results to normalized table."""
        conn = await self.create_connection()
        try:
            # Calculate totals
            total_passed = 0
            total_failed = 0
            total_suspect = 0

            # Insert individual AC results
            for ac_key in results.keys():
                if ac_key.startswith("ac") and isinstance(results[ac_key], dict):
                    ac_number = int(ac_key[2:])  # Extract number from 'ac1', 'ac2', etc.
                    ac_data = results[ac_key]

                    result_value = ac_data.get("result", "").lower()
                    if result_value == "pass":
                        total_passed += 1
                    elif result_value == "fail":
                        total_failed += 1
                    elif result_value == "suspect":
                        total_suspect += 1

                    await conn.execute(
                        """
                        INSERT INTO mtd_ac_results (
                            job_id, website_url, ac_number, ac_result, ac_confidence, ac_explanation, ai_model_used
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (job_id, website_url, ac_number) DO UPDATE SET
                            ac_result = EXCLUDED.ac_result,
                            ac_confidence = EXCLUDED.ac_confidence,
                            ac_explanation = EXCLUDED.ac_explanation,
                            ai_model_used = EXCLUDED.ai_model_used,
                            last_updated_date = NOW(),
                            version_num = mtd_ac_results.version_num + 1
                    """,
                        job_id,
                        website_url,
                        ac_number,
                        ac_data.get("result", ""),
                        ac_data.get("confidence", ""),
                        ac_data.get("explanation", ""),
                        ai_model,
                    )

            # Determine overall status
            if total_failed > 0 or total_suspect > 0:
                overall_status = "Fail"
            elif total_passed > 0:
                overall_status = "Pass"
            else:
                overall_status = "Unknown"

            # Insert summary
            await conn.execute(
                """
                INSERT INTO mtd_compliance_summary (
                    job_id, website_url, overall_status, 
                    total_passed, total_failed, total_suspect, ai_model_used
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (job_id, website_url) DO UPDATE SET
                    overall_status = EXCLUDED.overall_status,
                    total_passed = EXCLUDED.total_passed,
                    total_failed = EXCLUDED.total_failed,
                    total_suspect = EXCLUDED.total_suspect,
                    ai_model_used = EXCLUDED.ai_model_used,
                    last_updated_date = NOW(),
                    version_num = mtd_compliance_summary.version_num + 1
            """,
                job_id,
                website_url,
                overall_status,
                total_passed,
                total_failed,
                total_suspect,
                ai_model,
            )

            logger.info(
                "ac_results_saved",
                job_id=job_id,
                url=website_url,
                overall_status=overall_status,
                passed=total_passed,
                failed=total_failed,
                suspect=total_suspect,
            )

        finally:
            await conn.close()

    async def query_summary_by_job_id(self, job_id: str) -> List[Dict[str, Any]]:
        """Query summary results for a job_id."""
        conn = await self.create_connection()
        try:
            rows = await conn.fetch(
                """
                SELECT * FROM mtd_compliance_summary 
                WHERE job_id = $1 AND is_active = TRUE
                ORDER BY website_url
            """,
                job_id,
            )

            results = [dict(row) for row in rows]
            logger.info("summary_results_queried", job_id=job_id, count=len(results))
            return results

        finally:
            await conn.close()

    async def query_detailed_results_by_job_id(self, job_id: str) -> List[Dict[str, Any]]:
        """Query detailed AC results for a job_id."""
        conn = await self.create_connection()
        try:
            rows = await conn.fetch(
                """
                SELECT * FROM mtd_ac_results 
                WHERE job_id = $1 AND is_active = TRUE
                ORDER BY website_url, ac_number
            """,
                job_id,
            )

            results = [dict(row) for row in rows]
            logger.info("detailed_results_queried", job_id=job_id, count=len(results))
            return results

        finally:
            await conn.close()


class CoordinatorAgent:
    """Orchestrates the MTD compliance workflow."""

    def __init__(self, db_tools: MTDDatabaseTools, image_agent, reporting_agent):
        self.db_tools = db_tools
        self.image_agent = image_agent
        self.reporting_agent = reporting_agent

    async def process_job(self, job_id: str, website_urls: List[str]) -> str:
        """Process a complete MTD compliance job."""
        logger.info("coordinator_starting", job_id=job_id, url_count=len(website_urls))

        # Process each website
        for url in website_urls:
            try:
                await self.image_agent.analyze_website(job_id, url)
                await asyncio.sleep(1)  # Rate limiting
            except Exception as e:
                logger.error("website_analysis_failed", job_id=job_id, url=url, error=str(e))

        # Generate report
        report_path = await self.reporting_agent.generate_report(job_id)

        logger.info("coordinator_completed", job_id=job_id, report=report_path)
        return report_path


class SiteImageAnalysisAgent:
    """Performs MTD compliance checks on website screenshots."""

    def __init__(self, agent: Agent, db_tools: MTDDatabaseTools, model_id: str):
        self.agent = agent
        self.db_tools = db_tools
        self.model_id = model_id

    def create_image_message(self, image_data: bytes) -> str:
        """Create data URL for image."""
        image_b64 = base64.b64encode(image_data).decode("utf-8")
        return f"data:image/png;base64,{image_b64}"

    def create_mtd_compliance_prompt(self, website_url: str) -> str:
        """Create comprehensive MTD compliance check prompt."""
        return f"""
Analyze this website screenshot for Making Tax Digital (MTD) compliance. 

WEBSITE URL: {website_url}

Perform the following 10 acceptance criteria checks and return results in JSON format:

AC1: HTTPS Compliance - Must be a HTTPS (secure encryption) web address
AC2: Tax Product Link - Must provide link to the tax product with content relevant to service offered  
AC3: Privacy Statement - Must provide visible links to privacy statement
AC4: Terms & Conditions - Must provide visible links to Terms & Conditions
AC5: Functioning Website - Must be a fully functioning website (not partially constructed)
AC6: Personal Data - Must not request any personal customer data inappropriately
AC7: HMRC Branding - Must not use HMRC branding or logos inappropriately
AC8: HMRC Partnership - Must not claim to be in partnership with HMRC
AC9: HMRC Recognition - Must only use term 'HMRC Recognised' appropriately
AC10: Translation - Must be able to translate to English if foreign language product

For each AC, provide:
- result: Pass/Fail/Suspect
- confidence: High/Medium/Low  
- explanation: Brief reasoning (if result is Fail/Suspect)

RESPONSE FORMAT (JSON only, no other text):
{{
    "ac1": {{
        "result": "Pass/Fail",
        "confidence": "High/Medium/Low",
        "explanation": "Explanation if failed or suspect"
    }},
    "ac2": {{
        "result": "Pass/Fail", 
        "confidence": "High/Medium/Low",
        "explanation": "Explanation if failed or suspect"
    }},
    "ac3": {{
        "result": "Pass/Fail",
        "confidence": "High/Medium/Low", 
        "explanation": "Explanation if failed or suspect"
    }},
    "ac4": {{
        "result": "Pass/Fail",
        "confidence": "High/Medium/Low",
        "explanation": "Explanation if failed or suspect"
    }},
    "ac5": {{
        "result": "Pass/Fail",
        "confidence": "High/Medium/Low",
        "explanation": "Explanation if failed or suspect"
    }},
    "ac6": {{
        "result": "Pass/Fail",
        "confidence": "High/Medium/Low", 
        "explanation": "Explanation if failed or suspect"
    }},
    "ac7": {{
        "result": "Pass/Fail/Suspect",
        "confidence": "High/Medium/Low",
        "explanation": "Explanation if failed or suspect"
    }},
    "ac8": {{
        "result": "Pass/Fail",
        "confidence": "High/Medium/Low",
        "explanation": "Explanation if failed or suspect"
    }},
    "ac9": {{
        "result": "Pass/Fail",
        "confidence": "High/Medium/Low", 
        "explanation": "Explanation if failed or suspect"
    }},
    "ac10": {{
        "result": "Pass/Fail",
        "confidence": "High/Medium/Low",
        "explanation": "Explanation if failed or suspect"
    }}
}}
"""

    async def analyze_website(self, job_id: str, website_url: str):
        """Analyze a single website for MTD compliance."""
        logger.info("analyzing_website", job_id=job_id, url=website_url)

        # Fetch image from database
        image_data = await self.db_tools.fetch_image_from_db(job_id, website_url)
        if not image_data:
            logger.error("no_image_data", job_id=job_id, url=website_url)
            return

        try:
            # Create prompt and image message
            prompt = self.create_mtd_compliance_prompt(website_url)
            image_url = self.create_image_message(image_data)

            # Single LLM call with image and all AC checks
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ]

            response = await self.agent.arun(input=messages)

            # Parse response
            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            # Try to parse JSON response
            try:
                results = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown
                import re

                json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
                if json_match:
                    results = json.loads(json_match.group(1).strip())
                else:
                    logger.error("json_parse_failed", content=content[:500])
                    return

            # Save results to database
            await self.db_tools.save_ac_results(job_id, website_url, results, self.model_id)

            logger.info("website_analysis_completed", job_id=job_id, url=website_url)

        except Exception as e:
            logger.error("analysis_failed", job_id=job_id, url=website_url, error=str(e))
            raise


class ReportingAgent:
    """Generates CSV reports from MTD compliance results."""

    def __init__(self, db_tools: MTDDatabaseTools):
        self.db_tools = db_tools

    async def generate_report(self, job_id: str) -> str:
        """Generate CSV report for a job_id from normalized tables."""
        logger.info("generating_report", job_id=job_id)

        # Query both summary and detailed results
        summary_results = await self.db_tools.query_summary_by_job_id(job_id)
        detailed_results = await self.db_tools.query_detailed_results_by_job_id(job_id)

        if not summary_results:
            logger.warning("no_results_found", job_id=job_id)
            return None

        # Organize detailed results by website_url
        detailed_by_url = {}
        for detail in detailed_results:
            url = detail["website_url"]
            if url not in detailed_by_url:
                detailed_by_url[url] = {}
            detailed_by_url[url][detail["ac_number"]] = detail

        # Generate CSV report
        output_file = Path(
            f"./mtd_compliance_report_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "job_id",
                "website_url",
                "overall_status",
                "total_passed",
                "total_failed",
                "total_suspect",
                "ac1_result",
                "ac1_confidence",
                "ac1_explanation",
                "ac2_result",
                "ac2_confidence",
                "ac2_explanation",
                "ac3_result",
                "ac3_confidence",
                "ac3_explanation",
                "ac4_result",
                "ac4_confidence",
                "ac4_explanation",
                "ac5_result",
                "ac5_confidence",
                "ac5_explanation",
                "ac6_result",
                "ac6_confidence",
                "ac6_explanation",
                "ac7_result",
                "ac7_confidence",
                "ac7_explanation",
                "ac8_result",
                "ac8_confidence",
                "ac8_explanation",
                "ac9_result",
                "ac9_confidence",
                "ac9_explanation",
                "ac10_result",
                "ac10_confidence",
                "ac10_explanation",
                "analysis_timestamp",
                "ai_model_used",
            ]

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for summary in summary_results:
                website_url = summary["website_url"]
                website_details = detailed_by_url.get(website_url, {})

                row = {
                    "job_id": summary["job_id"],
                    "website_url": website_url,
                    "overall_status": summary["overall_status"],
                    "total_passed": summary["total_passed"],
                    "total_failed": summary["total_failed"],
                    "total_suspect": summary["total_suspect"],
                    "analysis_timestamp": summary["analysis_timestamp"],
                    "ai_model_used": summary["ai_model_used"],
                }

                # Extract each AC result from normalized data
                for ac_num in range(1, 11):
                    ac_data = website_details.get(ac_num, {})

                    row[f"ac{ac_num}_result"] = ac_data.get("ac_result", "")
                    row[f"ac{ac_num}_confidence"] = ac_data.get("ac_confidence", "")
                    row[f"ac{ac_num}_explanation"] = ac_data.get("ac_explanation", "")

                writer.writerow(row)

        logger.info(
            "report_generated", job_id=job_id, file=str(output_file), records=len(summary_results)
        )
        return str(output_file)


class MTDSiteChecker:
    """Main MTD Site Checker with 3-agent architecture."""

    def __init__(
        self,
        model_id: str,
        api_key: str,
        base_url: str,
        source_table: str = "preprocessing_results",
    ):
        self.model_id = model_id
        self.source_table = source_table

        # Database configuration
        self.db_config = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "site_analysis"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
        }

        # Initialize Agno model and agent
        self.model = OpenAILike(id=model_id, api_key=api_key, base_url=base_url)

        self.agent = Agent(model=self.model)

        # Initialize tools and agents
        self.db_tools = MTDDatabaseTools(self.db_config, source_table)
        self.image_agent = SiteImageAnalysisAgent(self.agent, self.db_tools, model_id)
        self.reporting_agent = ReportingAgent(self.db_tools)
        self.coordinator = CoordinatorAgent(self.db_tools, self.image_agent, self.reporting_agent)

        logger.info("mtd_checker_initialized", model_id=model_id, source_table=source_table)

    async def setup_database(self):
        """Ensure database tables exist."""
        await self.db_tools.ensure_tables_exist()

    async def run_mtd_analysis(self, job_id: str, website_urls: Optional[List[str]] = None) -> str:
        """Run MTD compliance analysis."""
        await self.setup_database()

        if website_urls is None:
            # Query all websites from source table for this job_id
            conn = await self.db_tools.create_connection()
            try:
                rows = await conn.fetch(
                    f"""
                    SELECT DISTINCT original_url FROM {self.source_table} 
                    WHERE job_id = $1 AND is_active = TRUE
                """,
                    job_id,
                )
                website_urls = [row["original_url"] for row in rows]
            finally:
                await conn.close()

        if not website_urls:
            logger.error("no_websites_found", job_id=job_id, table=self.source_table)
            return None

        logger.info(
            "websites_found", job_id=job_id, count=len(website_urls), table=self.source_table
        )

        # Run coordinator
        report_path = await self.coordinator.process_job(job_id, website_urls)
        return report_path


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="MTD Compliance Site Checker")
    parser.add_argument("--api-key", required=True, help="API key for the OpenAI-like model")
    parser.add_argument(
        "--base-url", required=True, help="Base URL for the OpenAI-like model endpoint"
    )
    parser.add_argument(
        "--model-id", default="gpt-4o-mini", help="Model ID to use (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--job-id", help="Job ID for batch processing (auto-generated if not provided)"
    )
    parser.add_argument(
        "--source-table", default="preprocessing_results", help="Source table name for images/data"
    )
    parser.add_argument(
        "--urls", nargs="+", help="Website URLs to analyze (if not reading from database)"
    )

    args = parser.parse_args()

    # Set up logging
    structlog.configure(
        processors=[structlog.processors.TimeStamper(fmt="ISO"), structlog.dev.ConsoleRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    try:
        checker = MTDSiteChecker(
            model_id=args.model_id,
            api_key=args.api_key,
            base_url=args.base_url,
            source_table=args.source_table,
        )

        # Generate job_id if not provided
        job_id = args.job_id or str(uuid.uuid4())

        # Run MTD analysis
        report_path = await checker.run_mtd_analysis(job_id, args.urls)

        if report_path:
            print(f"\n🎯 MTD Compliance Analysis Completed!")
            print(f"📊 Job ID: {job_id}")
            print(f"📄 Report saved to: {report_path}")
            print(f"🔗 Download link: file://{Path(report_path).absolute()}")
            print(f"📋 Source table: {args.source_table}")
        else:
            print("❌ Analysis failed or no data found")
            return 1

        return 0

    except Exception as e:
        logger.error("mtd_analysis_failed", error=str(e))
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
