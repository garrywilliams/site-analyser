"""Language analysis and translation capability agent using Agno framework."""

from datetime import datetime
from typing import List, Dict

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.anthropic import Claude
from agno.tools.reasoning import ReasoningTools
from pydantic import BaseModel
import structlog

from ..models.analysis import SiteAnalysisResult
from ..models.config import SiteAnalyserConfig

logger = structlog.get_logger()


class LanguageAnalysisResult(BaseModel):
    """Structured result for language analysis."""
    primary_language: str
    detected_languages: List[str]
    is_english: bool
    has_translation_capability: bool
    translation_methods: List[str]
    english_accessibility_score: float
    language_compliance_issues: List[str]
    reasoning: str


class LanguageAnalysisAgent:
    """Agno agent for analyzing language and translation capabilities."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        
        # Create the agent model
        if config.ai_config.provider == "openai":
            model = OpenAIChat(id="gpt-4o")
        else:
            model = Claude(id="claude-sonnet-4-20250514")
        
        # Create the agent for language analysis
        self.agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""
            You are a language and internationalization specialist focusing on website language compliance.
            Your expertise includes:
            
            1. Language detection and identification
            2. Website internationalization and localization
            3. Translation capability assessment
            4. English accessibility for international services
            5. Multi-language website functionality
            
            LANGUAGE COMPLIANCE REQUIREMENTS:
            
            FOR NON-ENGLISH WEBSITES:
            - Must provide clear English translation capability
            - Translation can be via built-in tools, language switchers, or external tools
            - Content must be accessible to English-speaking users
            - Essential business information should be translatable
            
            TRANSLATION METHODS TO LOOK FOR:
            - Language selector/switcher buttons or menus
            - Built-in translation widgets or tools
            - Google Translate integration or similar services
            - Multi-language versions of the site
            - English-language alternative pages or sections
            - Browser translation compatibility
            
            ACCEPTABLE SOLUTIONS:
            - Native English language support
            - Language switcher with English option
            - Translation widget or plugin
            - Alternative English pages/sections
            - Compatible with browser translation tools
            
            COMPLIANCE VIOLATIONS:
            - Foreign language site with no translation capability
            - Translation tools that don't work or are inaccessible
            - English content that is machine-translated incorrectly
            - Missing essential information in English
            
            Your task: Assess language accessibility and translation capabilities 
            to ensure English-speaking users can access essential business information.
            """,
            markdown=True,
            show_tool_calls=True,
            monitoring=False  # Disable telemetry
        )
    
    async def analyze_language_capabilities(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze website language and translation capabilities."""
        logger.info("language_analysis_agent_started", url=url)
        
        try:
            # Skip if no content available
            if not result.html_content:
                logger.info("language_analysis_skipped", url=url, reason="no_content")
                result.language_analysis = {
                    "primary_language": "unknown",
                    "detected_languages": [],
                    "is_english": False,
                    "has_translation_capability": False,
                    "translation_methods": [],
                    "english_accessibility_score": 0.0,
                    "language_compliance_issues": ["No content available for analysis"],
                    "reasoning": "Website content could not be retrieved"
                }
                return result
            
            # Prepare content for analysis (truncate if too long)
            content_preview = result.html_content[:8000] if len(result.html_content) > 8000 else result.html_content
            
            analysis_prompt = f"""
            Analyze this website for language and translation capabilities:
            
            Website URL: {url}
            Content: {content_preview}
            
            Assess:
            1. What is the primary language of the website?
            2. Are there other languages detected?
            3. Is the site primarily in English?
            4. Does the site provide translation capabilities?
            5. What translation methods are available?
            6. Can English speakers access essential information?
            
            Look for:
            - Language selector buttons or dropdowns
            - Translation widgets (Google Translate, etc.)
            - Multi-language navigation menus
            - English alternative pages or sections
            - Language-switching functionality
            - International/localization features
            
            RESPONSE FORMAT:
            PRIMARY_LANGUAGE: [detected primary language]
            ALL_LANGUAGES: [list all detected languages]
            IS_ENGLISH: [YES/NO]
            HAS_TRANSLATION: [YES/NO]
            TRANSLATION_METHODS: [list available translation options]
            ACCESSIBILITY_SCORE: [0.0-1.0 for English accessibility]
            ISSUES: [list any compliance problems]
            REASONING: [detailed analysis of language capabilities]
            """
            
            # Use Agno for analysis
            response = await self.agent.arun(analysis_prompt)
            response_text = str(response)
            logger.info("language_analysis_response_received", url=url, response_type="agno_success")
            
            # Parse response
            language_data = self._parse_language_response(response_text)
            result.language_analysis = language_data
            
            logger.info("language_analysis_completed", 
                       url=url, 
                       primary_language=language_data["primary_language"],
                       has_translation=language_data["has_translation_capability"])
                
        except Exception as e:
            logger.error("language_analysis_agent_exception", url=url, error=str(e))
            result.language_analysis = {
                "primary_language": "unknown",
                "detected_languages": [],
                "is_english": False,
                "has_translation_capability": False,
                "translation_methods": [],
                "english_accessibility_score": 0.0,
                "language_compliance_issues": [f"Analysis error: {str(e)}"],
                "reasoning": "Language analysis could not be completed"
            }
        
        return result
    
    def _parse_language_response(self, response_text: str) -> dict:
        """Parse the Agno response for language analysis."""
        # Default values
        language_data = {
            "primary_language": "unknown",
            "detected_languages": [],
            "is_english": False,
            "has_translation_capability": False,
            "translation_methods": [],
            "english_accessibility_score": 0.0,
            "language_compliance_issues": [],
            "reasoning": response_text[:500]  # Keep first 500 chars as reasoning
        }
        
        try:
            lines = response_text.split('\n')
            for line in lines:
                line = line.strip()
                
                if line.startswith('PRIMARY_LANGUAGE:'):
                    lang_text = line.split(':', 1)[1].strip()
                    if lang_text and lang_text != '[detected primary language]':
                        language_data["primary_language"] = lang_text.lower()
                        # Set is_english if primary language is English
                        language_data["is_english"] = 'english' in lang_text.lower()
                
                elif line.startswith('ALL_LANGUAGES:'):
                    langs_text = line.split(':', 1)[1].strip()
                    if langs_text and langs_text != '[list all detected languages]':
                        langs = [l.strip() for l in langs_text.replace('[', '').replace(']', '').split(',')]
                        language_data["detected_languages"] = [l for l in langs if l and len(l) > 1]
                
                elif line.startswith('IS_ENGLISH:'):
                    language_data["is_english"] = 'YES' in line.upper()
                
                elif line.startswith('HAS_TRANSLATION:'):
                    language_data["has_translation_capability"] = 'YES' in line.upper()
                
                elif line.startswith('TRANSLATION_METHODS:'):
                    methods_text = line.split(':', 1)[1].strip()
                    if methods_text and methods_text != '[list available translation options]':
                        methods = [m.strip() for m in methods_text.replace('[', '').replace(']', '').split(',')]
                        language_data["translation_methods"] = [m for m in methods if m and len(m) > 2]
                
                elif line.startswith('ACCESSIBILITY_SCORE:'):
                    try:
                        score_text = line.split(':', 1)[1].strip()
                        language_data["english_accessibility_score"] = float(score_text)
                    except (ValueError, IndexError):
                        # If not English but has translation, give partial score
                        if not language_data["is_english"] and language_data["has_translation_capability"]:
                            language_data["english_accessibility_score"] = 0.7
                        elif language_data["is_english"]:
                            language_data["english_accessibility_score"] = 1.0
                        else:
                            language_data["english_accessibility_score"] = 0.0
                
                elif line.startswith('ISSUES:'):
                    issues_text = line.split(':', 1)[1].strip()
                    if issues_text and issues_text != '[list any compliance problems]':
                        issues = [i.strip() for i in issues_text.replace('[', '').replace(']', '').split(',')]
                        language_data["language_compliance_issues"] = [i for i in issues if i and len(i) > 2]
                
                elif line.startswith('REASONING:'):
                    reasoning_text = line.split(':', 1)[1].strip()
                    if reasoning_text and reasoning_text != '[detailed analysis of language capabilities]':
                        language_data["reasoning"] = reasoning_text[:500]
            
            # Auto-generate compliance issues if needed
            if not language_data["is_english"] and not language_data["has_translation_capability"]:
                language_data["language_compliance_issues"].append(
                    f"Non-English website ({language_data['primary_language']}) without translation capability"
                )
        
        except Exception as e:
            logger.debug("language_response_parsing_error", error=str(e))
        
        return language_data