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
from agno.agent import Agent
from agno.models.openai import OpenAILike

# Load environment variables
load_dotenv()

logger = structlog.get_logger()

class SimpleSiteChecker:
    """Simplified site compliance checker using Agno agents."""
    
    def __init__(self, model_id: str = "gpt-4o-mini", api_key: str = "", base_url: str = "", skip_large_images: bool = False):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': os.getenv('POSTGRES_NAME', 'mtdsource'),
            'user': os.getenv('POSTGRES_USER', 'mtdsource'),
            'password': os.getenv('POSTGRES_PASSWORD', ''),
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
        self.skip_large_images = skip_large_images
        
        logger.info("agent_initialized", model_id=model_id, base_url=base_url, skip_large_images=skip_large_images)
    
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
    
    def estimate_image_tokens(self, image_data: bytes) -> int:
        """Estimate token count for base64 encoded image."""
        # Base64 encoding increases size by ~33%
        base64_size = len(image_data) * 4 // 3
        # Each base64 char is roughly 1 token (conservative estimate)
        return base64_size
    
    def should_split_analysis(self, prompt: str, image_data: Optional[bytes] = None) -> bool:
        """Determine if analysis should be split due to context limits."""
        estimated_tokens = self.estimate_token_count(prompt)
        
        if image_data:
            image_tokens = self.estimate_image_tokens(image_data)
            estimated_tokens += image_tokens
            logger.info("token_estimation", 
                       prompt_tokens=self.estimate_token_count(prompt),
                       image_tokens=image_tokens,
                       total_estimated=estimated_tokens)
        
        max_safe_tokens = 120000  # Leave 8k tokens for response
        
        return estimated_tokens > max_safe_tokens
    
    def resize_image_if_needed(self, image_data: bytes, max_dimension: int = 768, quality: int = 85) -> bytes:
        """Resize image if it's too large to reduce token usage."""
        try:
            from PIL import Image
            import io
            
            # Load image
            img = Image.open(io.BytesIO(image_data))
            
            # Check if resize is needed
            if max(img.width, img.height) <= max_dimension:
                return image_data  # No resize needed
            
            # Calculate new dimensions maintaining aspect ratio
            if img.width > img.height:
                new_width = max_dimension
                new_height = int((max_dimension * img.height) / img.width)
            else:
                new_height = max_dimension
                new_width = int((max_dimension * img.width) / img.height)
            
            # Resize image
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Save to bytes with aggressive compression
            output_buffer = io.BytesIO()
            
            # Try JPEG first for better compression (if not transparent)
            if resized_img.mode in ('RGBA', 'LA'):
                # Has transparency, stick with PNG but compress aggressively  
                resized_img.save(output_buffer, format='PNG', optimize=True, compress_level=9)
            else:
                # No transparency, use JPEG for much better compression
                if resized_img.mode != 'RGB':
                    resized_img = resized_img.convert('RGB')
                resized_img.save(output_buffer, format='JPEG', quality=quality, optimize=True)
            
            resized_data = output_buffer.getvalue()
            
            original_size = len(image_data)
            new_size = len(resized_data)
            compression_ratio = new_size / original_size
            
            logger.info("image_resized", 
                       original_size=original_size,
                       new_size=new_size,
                       compression_ratio=f"{compression_ratio:.2f}",
                       dimensions=f"{new_width}x{new_height}")
            
            return resized_data
            
        except Exception as e:
            logger.warning("image_resize_failed", error=str(e))
            return image_data  # Return original if resize fails
    
    def compress_image_aggressively(self, image_data: bytes, target_tokens: int = 50000) -> bytes:
        """Compress image more aggressively to fit token limits."""
        try:
            from PIL import Image
            import io
            
            img = Image.open(io.BytesIO(image_data))
            
            # Start with smaller dimensions and lower quality
            max_dim = 512
            quality = 60
            
            while max_dim >= 256:  # Don't go below 256px
                # Resize
                if max(img.width, img.height) > max_dim:
                    if img.width > img.height:
                        new_width = max_dim
                        new_height = int((max_dim * img.height) / img.width)
                    else:
                        new_height = max_dim
                        new_width = int((max_dim * img.width) / img.height)
                    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    resized_img = img
                
                # Compress
                output_buffer = io.BytesIO()
                if resized_img.mode != 'RGB':
                    resized_img = resized_img.convert('RGB')
                resized_img.save(output_buffer, format='JPEG', quality=quality, optimize=True)
                compressed_data = output_buffer.getvalue()
                
                # Check if it fits our token budget
                estimated_tokens = self.estimate_image_tokens(compressed_data)
                if estimated_tokens <= target_tokens:
                    logger.info("aggressive_compression_success", 
                               original_tokens=self.estimate_image_tokens(image_data),
                               final_tokens=estimated_tokens,
                               dimensions=f"{new_width if 'new_width' in locals() else img.width}x{new_height if 'new_height' in locals() else img.height}",
                               quality=quality)
                    return compressed_data
                
                # Try smaller dimensions and lower quality
                max_dim = int(max_dim * 0.8)
                quality = max(30, quality - 10)
            
            # If we still can't fit, return the most compressed version we tried
            logger.warning("aggressive_compression_insufficient", 
                          final_tokens=self.estimate_image_tokens(compressed_data),
                          target_tokens=target_tokens)
            return compressed_data
            
        except Exception as e:
            logger.warning("aggressive_compression_failed", error=str(e))
            return image_data
    
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
                elements = soup.find_all(string=lambda string: string and keyword.lower() in string.lower())
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
                logger.info("sending_image_to_agent", 
                           image_size=len(image_data), 
                           image_url_preview=image_url[:100] + "..." if len(image_url) > 100 else image_url)
                
                # Create message with both text and image - try Agno's expected format
                messages = [
                    {
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
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
            except json.JSONDecodeError as e:
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                if json_match:
                    try:
                        json_content = json_match.group(1).strip()
                        logger.info("extracted_json_from_markdown", json_preview=json_content[:200])
                        return json.loads(json_content)
                    except json.JSONDecodeError as e2:
                        logger.warning("markdown_json_parse_failed", 
                                     extracted_content=json_content[:300],
                                     parse_error=str(e2))
                
                logger.warning("json_parse_failed", 
                             raw_response_preview=content[:500] + "..." if len(content) > 500 else content,
                             parse_error=str(e))
                return {"raw_response": content, "parse_error": f"Failed to parse JSON: {str(e)}"}
                
        except Exception as e:
            logger.error("agent_call_failed", error=str(e))
            return {"error": str(e)}
    
    async def analyze_record(self, record: Dict) -> Dict:
        """Analyze a single database record with separate image and content analysis."""
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
        
        # Run both analyses concurrently for better performance
        visual_task = self.analyze_image_separately(record) if record['screenshot_image'] else None
        content_task = self.analyze_content_separately(record) if record['html_content'] else None
        
        # Wait for both to complete
        if visual_task and content_task:
            visual_results, content_results = await asyncio.gather(visual_task, content_task, return_exceptions=True)
        elif visual_task:
            visual_results = await visual_task
            content_results = {}
        elif content_task:
            content_results = await content_task
            visual_results = {}
        else:
            visual_results = {}
            content_results = {}
        
        # Handle exceptions
        if isinstance(visual_results, Exception):
            logger.error("visual_analysis_failed", id=record_id, error=str(visual_results))
            visual_results = {"error": str(visual_results)}
            
        if isinstance(content_results, Exception):
            logger.error("content_analysis_failed", id=record_id, error=str(content_results))
            content_results = {"error": str(content_results)}
        
        # Merge results
        merged_results = self.merge_analysis_results(visual_results, content_results)
        results.update(merged_results)
        
        return results
    
    async def analyze_image_separately(self, record: Dict) -> Dict:
        """Analyze image/screenshot separately with focused visual prompt."""
        company_name = record['company_name']
        url = record['original_url']
        record_id = record['id']
        
        try:
            # Optimize image for single-purpose analysis
            image_data = self.resize_image_if_needed(record['screenshot_image'], max_dimension=768, quality=75)
            
            # Create focused image-only prompt (much shorter)
            image_prompt = f"""Analyze this website screenshot for visual compliance issues:

COMPANY: {company_name}
URL: {url}

Assess for:
1. Making Tax Digital relevance (does this appear to be MTD/tax software/accounting services?)
2. UK Government visual violations (Crown logos, gov.uk styling, official colors)
3. HMRC visual violations (HMRC branding, tax authority styling)  
4. Design professionalism and trust indicators

JSON response only:
{{
    "mtd_relevant": {{"relevant": true/false, "confidence": "high/medium/low", "reasoning": "brief explanation"}},
    "govt_visual_violations": {{"found": true/false, "details": "brief description"}},
    "hmrc_visual_violations": {{"found": true/false, "details": "brief description"}},
    "design_quality": {{"professional": true/false, "issues": "main issues"}},
    "visual_risk_level": "none/low/medium/high",
    "summary": "One sentence visual assessment"
}}"""

            # Much smaller context - should almost always fit
            if self.should_split_analysis(image_prompt, image_data):
                # Try even more aggressive compression if needed
                compressed_image = self.compress_image_aggressively(image_data, target_tokens=30000)
                if self.should_split_analysis(image_prompt, compressed_image):
                    if self.skip_large_images:
                        return {"skipped": True, "reason": "Image too large"}
                    else:
                        # Ultra-minimal prompt as last resort
                        ultra_minimal = f"Analyze screenshot for government trademark violations. Company: {company_name}. Brief JSON response."
                        response = await self.call_agent(ultra_minimal, compressed_image)
                else:
                    response = await self.call_agent(image_prompt, compressed_image)
            else:
                response = await self.call_agent(image_prompt, image_data)
            
            logger.info("image_analysis_completed", id=record_id, response_keys=list(response.keys()) if isinstance(response, dict) else "non_dict_response")
            if isinstance(response, dict) and any(key in response for key in ['govt_visual_violations', 'hmrc_visual_violations']):
                logger.info("visual_violations_detected", id=record_id, 
                          govt_found=response.get('govt_visual_violations', {}).get('found'),
                          hmrc_found=response.get('hmrc_visual_violations', {}).get('found'))
            return response
            
        except Exception as e:
            logger.error("image_analysis_failed", id=record_id, error=str(e))
            return {"error": str(e)}
    
    async def analyze_content_separately(self, record: Dict) -> Dict:
        """Analyze HTML content separately with focused content prompt."""
        company_name = record['company_name']
        url = record['original_url']
        record_id = record['id']
        
        try:
            # Extract only the most relevant HTML content
            relevant_content = self.extract_relevant_html_content(record['html_content'])
            
            # Create focused content-only prompt (no image context needed)
            content_prompt = f"""Analyze this website content for compliance issues:

COMPANY: {company_name}
URL: {url}

CONTENT:
{relevant_content}

Assess for:
1. Making Tax Digital relevance (MTD software, tax services, accounting tools, VAT/bookkeeping)
2. UK Government trademark violations (unauthorized gov terms, Crown references)
3. HMRC trademark violations (unauthorized HMRC branding, misleading tax authority claims)
4. Business legitimacy (contact info, professional content, required legal pages)
5. Tax service compliance (appropriate disclaimers, qualification statements)

JSON response only:
{{
    "mtd_relevant": {{"relevant": true/false, "confidence": "high/medium/low", "reasoning": "brief explanation"}},
    "govt_content_violations": {{"found": true/false, "details": "brief description"}},
    "hmrc_content_violations": {{"found": true/false, "details": "brief description"}},
    "legitimacy_concerns": {{"found": true/false, "details": "main concerns"}},
    "tax_compliance": {{"compliant": true/false, "details": "compliance issues"}},
    "content_risk_level": "none/low/medium/high",
    "summary": "One sentence content assessment"
}}"""

            # Text-only analysis should be much smaller
            if self.should_split_analysis(content_prompt):
                # Further reduce content if still too large
                shorter_content = relevant_content[:1500]  # Even more aggressive
                content_prompt = content_prompt.replace(relevant_content, shorter_content)
            
            response = await self.call_agent(content_prompt)
            logger.info("content_analysis_completed", id=record_id)
            return response
            
        except Exception as e:
            logger.error("content_analysis_failed", id=record_id, error=str(e))
            return {"error": str(e)}
    
    def merge_analysis_results(self, visual_results: Dict, content_results: Dict) -> Dict:
        """Merge separate visual and content analysis into unified results for CSV."""
        merged = {
            'visual_analysis': visual_results,
            'content_analysis': content_results
        }
        
        # Create unified risk assessment
        visual_risk = visual_results.get('visual_risk_level', 'none')
        content_risk = content_results.get('content_risk_level', 'none')
        
        # Determine overall risk (take the higher of the two)
        risk_levels = {'none': 0, 'low': 1, 'medium': 2, 'high': 3}
        overall_risk_level = max(
            risk_levels.get(visual_risk, 0),
            risk_levels.get(content_risk, 0)
        )
        overall_risk = [k for k, v in risk_levels.items() if v == overall_risk_level][0]
        
        merged['overall_risk_assessment'] = overall_risk
        merged['analysis_method'] = 'separate_prompts'
        
        return merged
    
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
                # MTD relevance assessment
                'mtd_relevant_visual', 'mtd_confidence_visual', 'mtd_reasoning_visual',
                'mtd_relevant_content', 'mtd_confidence_content', 'mtd_reasoning_content',
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
                    # Add default MTD relevance if visual analysis failed
                    row.update({
                        'mtd_relevant_visual': 'Unknown',
                        'mtd_confidence_visual': 'none',
                        'mtd_reasoning_visual': 'Visual analysis failed',
                    })
                else:
                    row.update({
                        'mtd_relevant_visual': visual.get('mtd_relevant', {}).get('relevant', 'Unknown'),
                        'mtd_confidence_visual': visual.get('mtd_relevant', {}).get('confidence', 'low'),
                        'mtd_reasoning_visual': visual.get('mtd_relevant', {}).get('reasoning', 'No assessment available'),
                        'visual_govt_violations_found': visual.get('govt_visual_violations', {}).get('found', False),
                        'visual_govt_violations_severity': visual.get('govt_visual_violations', {}).get('severity', 'none'),
                        'visual_govt_violations_details': visual.get('govt_visual_violations', {}).get('details', 'No violations detected'),
                        'visual_hmrc_violations_found': visual.get('hmrc_visual_violations', {}).get('found', False),
                        'visual_hmrc_violations_severity': visual.get('hmrc_visual_violations', {}).get('severity', 'none'),
                        'visual_hmrc_violations_details': visual.get('hmrc_visual_violations', {}).get('details', 'No violations detected'),
                        'design_professional': visual.get('design_quality', {}).get('professional', True),
                        'design_issues': visual.get('design_quality', {}).get('issues', 'No issues detected'),
                        'trust_indicators_present': visual.get('trust_indicators', {}).get('present', True),
                        'trust_indicators_details': visual.get('trust_indicators', {}).get('details', 'Standard indicators present'),
                        'visual_risk': visual.get('visual_risk_level', 'none'),
                        'visual_summary': visual.get('summary', 'Visual analysis completed - no issues detected'),
                    })
                
                # Content analysis results
                content = result.get('content_analysis', {})
                if 'error' in content:
                    row['content_analysis_error'] = content['error']
                    # Add default MTD relevance if content analysis failed
                    row.update({
                        'mtd_relevant_content': 'Unknown',
                        'mtd_confidence_content': 'none',
                        'mtd_reasoning_content': 'Content analysis failed',
                    })
                else:
                    row.update({
                        'mtd_relevant_content': content.get('mtd_relevant', {}).get('relevant', 'Unknown'),
                        'mtd_confidence_content': content.get('mtd_relevant', {}).get('confidence', 'low'),
                        'mtd_reasoning_content': content.get('mtd_relevant', {}).get('reasoning', 'No assessment available'),
                        'uk_govt_violations_found': content.get('govt_content_violations', {}).get('found', False),
                        'uk_govt_violations_severity': content.get('govt_content_violations', {}).get('severity', 'none'),
                        'uk_govt_violations_details': content.get('govt_content_violations', {}).get('details', 'No violations detected'),
                        'hmrc_violations_found': content.get('hmrc_content_violations', {}).get('found', False),
                        'hmrc_violations_severity': content.get('hmrc_content_violations', {}).get('severity', 'none'),
                        'hmrc_violations_details': content.get('hmrc_content_violations', {}).get('details', 'No violations detected'),
                        'legitimacy_concerns_found': content.get('legitimacy_concerns', {}).get('found', False),
                        'legitimacy_concerns_severity': content.get('legitimacy_concerns', {}).get('severity', 'none'),
                        'legitimacy_concerns_details': content.get('legitimacy_concerns', {}).get('details', 'No concerns identified'),
                        'tax_compliance_compliant': content.get('tax_compliance', {}).get('compliant', True),
                        'tax_compliance_severity': content.get('tax_compliance', {}).get('severity', 'none'),
                        'tax_compliance_details': content.get('tax_compliance', {}).get('details', 'Compliant'),
                        'overall_risk': content.get('content_risk_level', 'none'),
                        'content_summary': content.get('summary', 'Content analysis completed - no issues detected'),
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
    parser.add_argument('--skip-large-images', action='store_true',
                        help='Skip image analysis if image is too large for context window')
    
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
            base_url=args.base_url,
            skip_large_images=args.skip_large_images
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