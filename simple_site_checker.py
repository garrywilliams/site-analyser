#!/usr/bin/env python3
"""
Simplified Site Checker - Proof of Concept
Processes active database records with Agno agents and outputs findings to CSV.
"""

import asyncio
import base64
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import asyncpg
import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = structlog.get_logger()

class SimpleSiteChecker:
    """Simplified site compliance checker using Agno agents."""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'database': os.getenv('DB_NAME', 'site_analysis'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', ''),
        }
        
        # AI configuration
        self.ai_provider = os.getenv('AI_PROVIDER', 'openai')
        self.ai_api_key = os.getenv('OPENAI_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
        
        if not self.ai_api_key:
            raise ValueError("Missing AI API key. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env")
    
    async def get_active_records(self, limit: Optional[int] = None) -> List[Dict]:
        """Fetch active records from database."""
        conn = await asyncpg.connect(**self.db_config)
        
        try:
            query = """
                SELECT id, job_id, company_name, original_url, final_url, domain,
                       screenshot_image, html_content, load_time_ms, redirected
                FROM site_analysis_data
                WHERE is_active = true AND analysis_status = 'pending'
                ORDER BY company_name, original_url
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            rows = await conn.fetch(query)
            records = [dict(row) for row in rows]
            
            logger.info("active_records_fetched", count=len(records))
            return records
            
        finally:
            await conn.close()
    
    def encode_image_for_ai(self, image_data: bytes) -> str:
        """Encode image data as base64 for AI APIs."""
        return base64.b64encode(image_data).decode('utf-8')
    
    def create_compliance_prompt(self, company_name: str, url: str, html_content: str) -> str:
        """Create a comprehensive compliance assessment prompt."""
        # Truncate HTML if too long (keep first 8000 chars for context)
        html_snippet = html_content[:8000] + "..." if len(html_content) > 8000 else html_content
        
        prompt = f"""
Analyze this website for UK Government and HMRC trademark compliance and general business legitimacy issues.

COMPANY: {company_name}
URL: {url}

ASSESSMENT CRITERIA:
1. UK Government Trademark Violations:
   - Unauthorized use of Crown copyright, government logos, or official emblems
   - Misleading use of "gov.uk", "HMRC", "HM Revenue", or similar official terminology
   - Impersonation of government services or officials

2. HMRC Trademark Violations:
   - Unauthorized use of HMRC branding, logos, or terminology
   - Misleading claims about HMRC endorsement or official status
   - Use of HMRC-like visual design or color schemes inappropriately

3. Business Legitimacy Concerns:
   - Incomplete or missing contact information
   - Unprofessional design or numerous errors
   - Suspicious payment requests or pricing structures
   - Missing privacy policy, terms of service, or other required legal pages

4. Tax Service Compliance:
   - Appropriate disclaimers about tax advice limitations
   - Clear qualification statements from tax professionals
   - Proper regulatory compliance mentions (if applicable)

HTML CONTENT:
{html_snippet}

INSTRUCTIONS:
Provide your assessment in this exact JSON format:
{{
    "uk_govt_violations": {{
        "found": true/false,
        "severity": "none/low/medium/high",
        "details": "specific violations found or 'None detected'"
    }},
    "hmrc_violations": {{
        "found": true/false,
        "severity": "none/low/medium/high", 
        "details": "specific violations found or 'None detected'"
    }},
    "legitimacy_concerns": {{
        "found": true/false,
        "severity": "none/low/medium/high",
        "details": "specific concerns found or 'None detected'"
    }},
    "tax_compliance": {{
        "compliant": true/false,
        "severity": "none/low/medium/high",
        "details": "compliance issues or 'Compliant'"
    }},
    "overall_risk": "none/low/medium/high",
    "summary": "Brief 1-2 sentence summary of main findings"
}}

Respond ONLY with valid JSON - no other text.
"""
        return prompt
    
    def create_visual_analysis_prompt(self, company_name: str, url: str) -> str:
        """Create a visual analysis prompt for screenshot assessment."""
        prompt = f"""
Analyze this website screenshot for visual trademark violations and design concerns.

COMPANY: {company_name}
URL: {url}

VISUAL ASSESSMENT CRITERIA:
1. Government Visual Violations:
   - Crown logos, royal arms, or government emblems
   - Official government color schemes (green/white gov.uk style)
   - Government-style headers, footers, or navigation

2. HMRC Visual Violations:
   - HMRC logos, branding, or visual identity
   - Official tax authority styling or imagery
   - HMRC-like forms or document layouts

3. Design Quality Issues:
   - Unprofessional appearance or layout problems
   - Broken images, misaligned elements, or poor typography
   - Suspicious or misleading visual elements

4. Trust Indicators:
   - Professional design and branding consistency
   - Clear company identification and contact visibility
   - Appropriate use of security badges or certifications

INSTRUCTIONS:
Provide your assessment in this exact JSON format:
{{
    "visual_govt_violations": {{
        "found": true/false,
        "severity": "none/low/medium/high",
        "details": "specific visual violations or 'None detected'"
    }},
    "visual_hmrc_violations": {{
        "found": true/false,
        "severity": "none/low/medium/high",
        "details": "specific visual violations or 'None detected'"
    }},
    "design_quality": {{
        "professional": true/false,
        "issues": "design problems found or 'None detected'"
    }},
    "trust_indicators": {{
        "present": true/false,
        "details": "trust elements observed or 'Limited indicators'"
    }},
    "visual_risk": "none/low/medium/high",
    "visual_summary": "Brief visual assessment summary"
}}

Respond ONLY with valid JSON - no other text.
"""
        return prompt
    
    async def call_ai_api(self, prompt: str, image_data: Optional[bytes] = None) -> Dict:
        """Call AI API with prompt and optional image."""
        try:
            if self.ai_provider == 'openai':
                return await self._call_openai(prompt, image_data)
            elif self.ai_provider == 'anthropic':
                return await self._call_anthropic(prompt, image_data)
            else:
                raise ValueError(f"Unsupported AI provider: {self.ai_provider}")
        except Exception as e:
            logger.error("ai_api_call_failed", error=str(e), provider=self.ai_provider)
            return {"error": str(e)}
    
    async def _call_openai(self, prompt: str, image_data: Optional[bytes] = None) -> Dict:
        """Call OpenAI GPT-4 Vision API."""
        import openai
        
        client = openai.AsyncOpenAI(
            api_key=self.ai_api_key,
            base_url=os.getenv('OPENAI_BASE_URL')  # Support for custom endpoints
        )
        
        messages = []
        
        if image_data:
            # Vision request with image
            image_b64 = self.encode_image_for_ai(image_data)
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                ]
            })
        else:
            # Text-only request
            messages.append({"role": "user", "content": prompt})
        
        response = await client.chat.completions.create(
            model="gpt-4o",  # Use GPT-4o for vision + text
            messages=messages,
            max_tokens=1000,
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        
        # Try to parse as JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_response": content, "parse_error": "Failed to parse JSON"}
    
    async def _call_anthropic(self, prompt: str, image_data: Optional[bytes] = None) -> Dict:
        """Call Anthropic Claude Vision API."""
        import anthropic
        
        client = anthropic.AsyncAnthropic(api_key=self.ai_api_key)
        
        content_parts = [{"type": "text", "text": prompt}]
        
        if image_data:
            image_b64 = self.encode_image_for_ai(image_data)
            content_parts.insert(0, {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_b64
                }
            })
        
        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": content_parts}],
            max_tokens=1000,
            temperature=0.1
        )
        
        content = response.content[0].text
        
        # Try to parse as JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_response": content, "parse_error": "Failed to parse JSON"}
    
    async def analyze_record(self, record: Dict) -> Dict:
        """Analyze a single database record."""
        company_name = record['company_name']
        url = record['original_url']
        record_id = record['id']
        
        logger.info("analyzing_record", id=record_id, company=company_name, url=url)
        
        results = {
            'id': record_id,
            'company_name': company_name,
            'url': url,
            'final_url': record.get('final_url'),
            'redirected': record.get('redirected', False),
            'load_time_ms': record.get('load_time_ms'),
            'analysis_timestamp': datetime.now().isoformat(),
        }
        
        # 1. Visual Analysis (if we have screenshot data)
        visual_results = {}
        if record['screenshot_image']:
            try:
                visual_prompt = self.create_visual_analysis_prompt(company_name, url)
                visual_response = await self.call_ai_api(visual_prompt, record['screenshot_image'])
                visual_results = visual_response
                logger.info("visual_analysis_completed", id=record_id)
            except Exception as e:
                logger.error("visual_analysis_failed", id=record_id, error=str(e))
                visual_results = {"error": str(e)}
        
        # 2. Content Analysis (if we have HTML)
        content_results = {}
        if record['html_content']:
            try:
                content_prompt = self.create_compliance_prompt(company_name, url, record['html_content'])
                content_response = await self.call_ai_api(content_prompt)
                content_results = content_response
                logger.info("content_analysis_completed", id=record_id)
            except Exception as e:
                logger.error("content_analysis_failed", id=record_id, error=str(e))
                content_results = {"error": str(e)}
        
        # Combine results
        results.update({
            'visual_analysis': visual_results,
            'content_analysis': content_results
        })
        
        return results
    
    async def mark_record_processed(self, record_id: int) -> None:
        """Mark a record as processed in the database."""
        conn = await asyncpg.connect(**self.db_config)
        
        try:
            await conn.execute(
                "UPDATE site_analysis_data SET analysis_status = 'completed', processed_at = NOW() WHERE id = $1",
                record_id
            )
            logger.info("record_marked_completed", id=record_id)
        finally:
            await conn.close()
    
    def save_results_to_csv(self, results: List[Dict], output_file: Path) -> None:
        """Save analysis results to CSV file."""
        if not results:
            logger.warning("no_results_to_save")
            return
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'id', 'company_name', 'url', 'final_url', 'redirected', 'load_time_ms',
                'analysis_timestamp',
                # Visual analysis fields
                'visual_govt_violations_found', 'visual_govt_violations_severity', 'visual_govt_violations_details',
                'visual_hmrc_violations_found', 'visual_hmrc_violations_severity', 'visual_hmrc_violations_details',
                'design_professional', 'design_issues',
                'trust_indicators_present', 'trust_indicators_details',
                'visual_risk', 'visual_summary',
                # Content analysis fields
                'uk_govt_violations_found', 'uk_govt_violations_severity', 'uk_govt_violations_details',
                'hmrc_violations_found', 'hmrc_violations_severity', 'hmrc_violations_details',
                'legitimacy_concerns_found', 'legitimacy_concerns_severity', 'legitimacy_concerns_details',
                'tax_compliance_compliant', 'tax_compliance_severity', 'tax_compliance_details',
                'overall_risk', 'content_summary',
                # Error tracking
                'visual_analysis_error', 'content_analysis_error'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                # Flatten the nested results into CSV row
                row = {
                    'id': result['id'],
                    'company_name': result['company_name'],
                    'url': result['url'],
                    'final_url': result.get('final_url', ''),
                    'redirected': result.get('redirected', False),
                    'load_time_ms': result.get('load_time_ms', ''),
                    'analysis_timestamp': result['analysis_timestamp'],
                }
                
                # Visual analysis results
                visual = result.get('visual_analysis', {})
                if 'error' in visual:
                    row['visual_analysis_error'] = visual['error']
                else:
                    row.update({
                        'visual_govt_violations_found': visual.get('visual_govt_violations', {}).get('found', ''),
                        'visual_govt_violations_severity': visual.get('visual_govt_violations', {}).get('severity', ''),
                        'visual_govt_violations_details': visual.get('visual_govt_violations', {}).get('details', ''),
                        'visual_hmrc_violations_found': visual.get('visual_hmrc_violations', {}).get('found', ''),
                        'visual_hmrc_violations_severity': visual.get('visual_hmrc_violations', {}).get('severity', ''),
                        'visual_hmrc_violations_details': visual.get('visual_hmrc_violations', {}).get('details', ''),
                        'design_professional': visual.get('design_quality', {}).get('professional', ''),
                        'design_issues': visual.get('design_quality', {}).get('issues', ''),
                        'trust_indicators_present': visual.get('trust_indicators', {}).get('present', ''),
                        'trust_indicators_details': visual.get('trust_indicators', {}).get('details', ''),
                        'visual_risk': visual.get('visual_risk', ''),
                        'visual_summary': visual.get('visual_summary', ''),
                    })
                
                # Content analysis results
                content = result.get('content_analysis', {})
                if 'error' in content:
                    row['content_analysis_error'] = content['error']
                else:
                    row.update({
                        'uk_govt_violations_found': content.get('uk_govt_violations', {}).get('found', ''),
                        'uk_govt_violations_severity': content.get('uk_govt_violations', {}).get('severity', ''),
                        'uk_govt_violations_details': content.get('uk_govt_violations', {}).get('details', ''),
                        'hmrc_violations_found': content.get('hmrc_violations', {}).get('found', ''),
                        'hmrc_violations_severity': content.get('hmrc_violations', {}).get('severity', ''),
                        'hmrc_violations_details': content.get('hmrc_violations', {}).get('details', ''),
                        'legitimacy_concerns_found': content.get('legitimacy_concerns', {}).get('found', ''),
                        'legitimacy_concerns_severity': content.get('legitimacy_concerns', {}).get('severity', ''),
                        'legitimacy_concerns_details': content.get('legitimacy_concerns', {}).get('details', ''),
                        'tax_compliance_compliant': content.get('tax_compliance', {}).get('compliant', ''),
                        'tax_compliance_severity': content.get('tax_compliance', {}).get('severity', ''),
                        'tax_compliance_details': content.get('tax_compliance', {}).get('details', ''),
                        'overall_risk': content.get('overall_risk', ''),
                        'content_summary': content.get('summary', ''),
                    })
                
                writer.writerow(row)
        
        logger.info("results_saved_to_csv", file=str(output_file), count=len(results))
    
    async def run_analysis(self, limit: Optional[int] = None, output_file: Optional[Path] = None, mark_completed: bool = True) -> List[Dict]:
        """Run the complete analysis workflow."""
        logger.info("starting_site_analysis", limit=limit, ai_provider=self.ai_provider)
        
        # Get active records
        records = await self.get_active_records(limit)
        
        if not records:
            logger.info("no_active_records_found")
            return []
        
        # Analyze each record
        results = []
        
        for i, record in enumerate(records, 1):
            logger.info("processing_record", current=i, total=len(records), 
                       id=record['id'], company=record['company_name'])
            
            try:
                result = await self.analyze_record(record)
                results.append(result)
                
                # Mark as processed if requested
                if mark_completed:
                    await self.mark_record_processed(record['id'])
                
                # Add small delay to be nice to AI APIs
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error("record_analysis_failed", id=record['id'], error=str(e))
                # Continue with next record
                continue
        
        # Save results to CSV
        if output_file:
            self.save_results_to_csv(results, output_file)
        
        logger.info("analysis_completed", total_records=len(records), successful=len(results))
        return results

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Simple Site Compliance Checker - Proof of Concept')
    parser.add_argument('--limit', type=int, help='Limit number of records to process')
    parser.add_argument('--output', type=Path, default=Path('./results/compliance_analysis.csv'),
                        help='Output CSV file path')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run analysis without marking records as completed')
    parser.add_argument('--ai-provider', choices=['openai', 'anthropic'],
                        help='AI provider to use (overrides env var)')
    
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
    
    # Override AI provider if specified
    if args.ai_provider:
        os.environ['AI_PROVIDER'] = args.ai_provider
    
    try:
        checker = SimpleSiteChecker()
        
        results = await checker.run_analysis(
            limit=args.limit,
            output_file=args.output,
            mark_completed=not args.dry_run
        )
        
        if results:
            print(f"\n✅ Analysis completed successfully!")
            print(f"📊 Processed {len(results)} records")
            print(f"📄 Results saved to: {args.output}")
            print(f"🎯 Records marked as completed: {not args.dry_run}")
        else:
            print("📭 No active records found to process")
        
        return 0
        
    except Exception as e:
        logger.error("analysis_failed", error=str(e))
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))