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
from agno import Agent
from agno.models.openai import OpenAILike

# Load environment variables
load_dotenv()

logger = structlog.get_logger()

class SimpleSiteChecker:
    """Simplified site compliance checker using Agno agents."""
    
    def __init__(self, model_id: str = "gpt-4o-mini", api_key: str = "", base_url: str = ""):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'database': os.getenv('DB_NAME', 'site_analysis'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', ''),
        }
        
        # Initialize Agno model and agent
        if not api_key or not base_url:
            raise ValueError("Both api_key and base_url are required for OpenAILike model")
        
        self.model = OpenAILike(
            id=model_id,
            api_key=api_key,
            base_url=base_url
        )
        
        self.agent = Agent(model=self.model)
        
        logger.info("agent_initialized", model_id=model_id, base_url=base_url)
    
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
    
    def create_image_message(self, image_data: bytes) -> str:
        """Create data URL for image to be used with Agno agent."""
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        return f"data:image/png;base64,{image_b64}"
    
    def estimate_token_count(self, text: str) -> int:
        """Rough estimate of token count (4 chars ≈ 1 token)."""
        return len(text) // 4
    
    def should_split_analysis(self, prompt: str, has_image: bool = False) -> bool:
        """Determine if analysis should be split due to context limits."""
        # Rough estimates:
        # - Base prompt: ~500-1000 tokens
        # - Image: ~1000-2000 tokens (depending on size/detail)
        # - HTML content: variable
        # - Safety margin: 20% of 128k = ~25k tokens
        
        estimated_tokens = self.estimate_token_count(prompt)
        if has_image:
            estimated_tokens += 1500  # Image overhead
        
        max_safe_tokens = 100000  # Leave 28k tokens for response
        
        return estimated_tokens > max_safe_tokens
    
    def extract_relevant_html_content(self, html_content: str) -> str:
        """Extract only relevant parts of HTML for analysis."""
        from bs4 import BeautifulSoup
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract key elements for compliance analysis
            relevant_content = []
            
            # 1. Title and meta
            if soup.title:
                relevant_content.append(f"TITLE: {soup.title.get_text().strip()}")
            
            # 2. Meta descriptions
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                relevant_content.append(f"META_DESCRIPTION: {meta_desc.get('content', '').strip()}")
            
            # 3. Main headings (h1, h2, h3)
            headings = []
            for tag in ['h1', 'h2', 'h3']:
                for element in soup.find_all(tag):
                    text = element.get_text().strip()
                    if text and len(text) < 200:  # Avoid overly long headings
                        headings.append(f"{tag.upper()}: {text}")
            
            if headings:
                relevant_content.append("HEADINGS:")
                relevant_content.extend(headings[:10])  # Max 10 headings
            
            # 4. Navigation and menu items (potential gov/HMRC terminology)
            nav_items = []
            for nav in soup.find_all(['nav', 'menu']):
                for link in nav.find_all('a'):
                    text = link.get_text().strip()
                    if text and len(text) < 100:
                        nav_items.append(text)
            
            if nav_items:
                relevant_content.append("NAVIGATION:")
                relevant_content.extend(nav_items[:15])  # Max 15 nav items
            
            # 5. Footer content (often contains company/legal info)
            footer = soup.find('footer')
            if footer:
                footer_text = footer.get_text().strip()
                if footer_text:
                    relevant_content.append(f"FOOTER: {footer_text[:1000]}")  # First 1000 chars
            
            # 6. Look for specific compliance-related terms
            compliance_keywords = [
                'privacy policy', 'terms of service', 'cookie policy', 'gdpr',
                'hmrc', 'tax', 'vat', 'government', 'crown', 'official',
                'contact', 'about', 'disclaimer', 'legal'
            ]
            
            compliance_content = []
            for keyword in compliance_keywords:
                # Find elements containing these keywords
                elements = soup.find_all(text=lambda text: text and keyword.lower() in text.lower())
                for element in elements[:3]:  # Max 3 per keyword
                    parent_text = element.parent.get_text().strip() if element.parent else str(element).strip()
                    if len(parent_text) < 500:  # Reasonable length
                        compliance_content.append(parent_text)
            
            if compliance_content:
                relevant_content.append("COMPLIANCE_CONTENT:")
                relevant_content.extend(list(set(compliance_content))[:10])  # Dedupe and limit
            
            # Join all content
            extracted_content = "\n".join(relevant_content)
            
            # Final length check - aim for ~4000 chars max
            if len(extracted_content) > 4000:
                extracted_content = extracted_content[:4000] + "... [TRUNCATED]"
            
            return extracted_content
            
        except Exception as e:
            logger.warning("html_extraction_failed", error=str(e))
            # Fallback to simple truncation
            return html_content[:3000] + "... [EXTRACTION_FAILED]"
    
    def create_compliance_prompt(self, company_name: str, url: str, html_content: str) -> str:
        """Create a comprehensive compliance assessment prompt."""
        # Extract only relevant HTML content
        html_snippet = self.extract_relevant_html_content(html_content)
        
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
    
    def create_short_visual_prompt(self, company_name: str, url: str) -> str:
        """Create a shorter visual analysis prompt for context-limited scenarios."""
        prompt = f"""
Analyze this website screenshot for trademark violations and design quality.

COMPANY: {company_name}
URL: {url}

Assess for:
1. Government/HMRC visual violations (logos, branding, color schemes)
2. Overall design quality and professionalism
3. Trust indicators and legitimacy concerns

JSON format:
{{
    "visual_govt_violations": {{"found": true/false, "severity": "none/low/medium/high", "details": "brief details"}},
    "visual_hmrc_violations": {{"found": true/false, "severity": "none/low/medium/high", "details": "brief details"}},
    "design_quality": {{"professional": true/false, "issues": "main issues or none"}},
    "trust_indicators": {{"present": true/false, "details": "key indicators"}},
    "visual_risk": "none/low/medium/high",
    "visual_summary": "One sentence summary"
}}

Respond ONLY with valid JSON.
"""
        return prompt
    
    async def call_agent(self, prompt: str, image_data: Optional[bytes] = None) -> Dict:
        """Call Agno agent with prompt and optional image."""
        try:
            if image_data:
                # Vision request with image
                image_url = self.create_image_message(image_data)
                # Create message with both text and image
                messages = [
                    {"role": "user", "content": f"Image: {image_url}\n\n{prompt}"}
                ]
                
                # Run agent with image context
                response = await self.agent.arun(messages=messages)
            else:
                # Text-only request
                response = await self.agent.arun(prompt)
            
            # Response should be a string, try to parse as JSON
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = str(response)
            
            # Try to parse as JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"raw_response": content, "parse_error": "Failed to parse JSON"}
                
        except Exception as e:
            logger.error("agent_call_failed", error=str(e))
            return {"error": str(e)}
    
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
                
                # Check if we need to do image-only analysis
                if self.should_split_analysis(visual_prompt, has_image=True):
                    logger.info("using_image_only_analysis", id=record_id, reason="context_too_large")
                    # Use a shorter prompt for image analysis
                    short_visual_prompt = self.create_short_visual_prompt(company_name, url)
                    visual_response = await self.call_agent(short_visual_prompt, record['screenshot_image'])
                else:
                    visual_response = await self.call_agent(visual_prompt, record['screenshot_image'])
                
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
                
                # Check token count and adjust if needed
                if self.should_split_analysis(content_prompt):
                    logger.info("using_minimal_content_analysis", id=record_id, reason="context_too_large")
                    # Use shorter extracted content
                    shorter_content = self.extract_relevant_html_content(record['html_content'])[:2000]
                    content_prompt = self.create_compliance_prompt(company_name, url, shorter_content)
                
                content_response = await self.call_agent(content_prompt)
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
        logger.info("starting_site_analysis", limit=limit, model_id=self.model.id)
        
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
    parser.add_argument('--api-key', required=True, help='API key for the OpenAI-like model')
    parser.add_argument('--base-url', required=True, help='Base URL for the OpenAI-like model endpoint')
    parser.add_argument('--model-id', default='gpt-4o-mini', help='Model ID to use (default: gpt-4o-mini)')
    parser.add_argument('--limit', type=int, help='Limit number of records to process')
    parser.add_argument('--output', type=Path, default=Path('./results/compliance_analysis.csv'),
                        help='Output CSV file path')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run analysis without marking records as completed')
    
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
    
    try:
        checker = SimpleSiteChecker(
            model_id=args.model_id,
            api_key=args.api_key,
            base_url=args.base_url
        )
        
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