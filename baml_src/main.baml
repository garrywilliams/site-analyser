generator lang_python {
  output_type python/pydantic
  output_dir "../site_analyser/baml_client"
  version "0.66.0"
}

client<llm> GPT4Vision {
  provider openai
  options {
    model gpt-4o
    max_tokens 2000
    temperature 0.1
  }
}

client<llm> ClaudeVision {
  provider anthropic
  options {
    model claude-sonnet-4-20250514
    max_tokens 2000
    temperature 0.1
  }
}

// Trademark violation detection types
enum ViolationType {
  UK_GOVERNMENT_LOGO
  HMRC_LOGO
  NHS_LOGO
  GOV_UK_BRANDING
  HMRC_COLOR_SCHEME
  GOVERNMENTAL_DESIGN
  COPYRIGHT_INFRINGEMENT
}

// Confidence levels for violations
enum ConfidenceLevel {
  HIGH
  MEDIUM
  LOW
}

// Data model for trademark violation
class TrademarkViolation {
  violation_type ViolationType
  confidence ConfidenceLevel
  confidence_score float
  description string
  location string?
  coordinates BoundingBox?
}

// Bounding box for violation location
class BoundingBox {
  x int
  y int
  width int
  height int
}

// Analysis result containing all violations
class TrademarkAnalysisResult {
  violations TrademarkViolation[]
  overall_assessment string
  risk_level ConfidenceLevel
  recommendations string[]
}

// BAML function for UK Government trademark analysis
function AnalyzeUKGovernmentTrademarks(image: image, url: string, context: string?) -> TrademarkAnalysisResult {
  client GPT4Vision
  prompt #"
    You are a trademark compliance expert specializing in UK Government and HMRC branding violations.

    Analyze the provided website screenshot for potential trademark violations of UK Government intellectual property.
    
    Website URL: {{ url }}
    {% if context %}
    Additional Context: {{ context }}
    {% endif %}

    SPECIFIC VIOLATIONS TO DETECT:

    1. **UK_GOVERNMENT_LOGO**: Official government logos (Crown, GOV.UK logo, department logos)
    2. **HMRC_LOGO**: HM Revenue and Customs official logos or branding
    3. **NHS_LOGO**: National Health Service logos or distinctive NHS branding
    4. **GOV_UK_BRANDING**: Official GOV.UK visual identity, fonts, or styling
    5. **HMRC_COLOR_SCHEME**: HMRC's distinctive green and white color scheme when used in official context
    6. **GOVERNMENTAL_DESIGN**: Overall design mimicking official government websites
    7. **COPYRIGHT_INFRINGEMENT**: Use of copyrighted government imagery or content

    ANALYSIS CRITERIA:

    - **HIGH confidence**: Clear, unmistakable use of official logos, exact color matching, identical layouts
    - **MEDIUM confidence**: Similar styling, unofficial variations of official elements
    - **LOW confidence**: Vague resemblance, generic governmental appearance

    For each violation found:
    1. Specify the exact violation type from the enum
    2. Provide confidence level (HIGH/MEDIUM/LOW) and numeric score (0.0-1.0)
    3. Give detailed description of what you observed
    4. Indicate location on page if possible
    5. Estimate bounding box coordinates if violation has clear boundaries

    IMPORTANT INSTRUCTIONS:
    - Only flag genuine trademark violations, not legitimate government services
    - Consider context - official government sites are allowed to use government branding
    - Be conservative with HIGH confidence ratings
    - Provide actionable recommendations for compliance
    - Focus on visual elements that could confuse users about site authenticity

    Return a structured analysis with all violations found, overall risk assessment, and compliance recommendations.
  "#
}

// Alternative BAML function using Claude for comparison
function AnalyzeUKGovTrademarksWithClaude(image: image, url: string, context: string?) -> TrademarkAnalysisResult {
  client ClaudeVision
  prompt #"
    As a UK trademark compliance specialist, examine this website screenshot for unauthorized use of UK Government intellectual property.

    Target URL: {{ url }}
    {% if context %}
    Context: {{ context }}
    {% endif %}

    TRADEMARK CATEGORIES TO ASSESS:

    **Official Logos & Symbols**
    - UK Government Crown logos
    - GOV.UK official branding
    - HMRC logos and symbols
    - NHS branding elements
    - Department-specific logos

    **Visual Identity Elements**
    - Official color schemes (especially HMRC green/white)
    - Typography matching government standards
    - Layout patterns mimicking GOV.UK
    - Official imagery and photography

    **Content & Messaging**
    - Use of official government language
    - Authoritative tone suggesting government backing
    - Official-sounding disclaimers or legal text

    CONFIDENCE ASSESSMENT:
    - HIGH (0.8-1.0): Definitive trademark violation with clear evidence
    - MEDIUM (0.4-0.7): Likely violation requiring investigation
    - LOW (0.1-0.3): Potential concern but unclear evidence

    For each violation identified:
    1. Classify using the violation type enum
    2. Assign confidence level and numeric score
    3. Describe the specific elements that constitute the violation
    4. Note the location within the page layout
    5. Estimate coordinates if the violation has defined boundaries

    COMPLIANCE FOCUS:
    - Distinguish between legitimate government sites and impersonation
    - Consider user confusion potential
    - Evaluate overall deceptive intent
    - Provide specific remediation steps

    Deliver comprehensive analysis with violation details, risk assessment, and actionable compliance recommendations.
  "#
}

// BAML function for policy detection and analysis
function AnalyzePolicyLinks(image: image, html_content: string?, url: string) -> PolicyAnalysisResult {
  client GPT4Vision
  prompt #"
    Analyze this website for privacy policy and terms & conditions compliance.

    Website URL: {{ url }}
    
    {% if html_content %}
    HTML Content Available: Yes (will be used for primary analysis)
    {% else %}
    HTML Content: Not available (analyzing screenshot only)
    {% endif %}

    DETECTION OBJECTIVES:

    1. **Privacy Policy Detection**
       - Look for "Privacy Policy", "Privacy Notice", "Data Protection" links
       - Check footer, header, and main navigation areas
       - Verify link accessibility and functionality

    2. **Terms & Conditions Detection**
       - Find "Terms", "Terms of Service", "Terms & Conditions", "Legal" links
       - Check standard locations (footer, legal sections)
       - Assess link visibility and accessibility

    ANALYSIS REQUIREMENTS:
    - Note exact text used for policy links
    - Identify location within page layout
    - Assess link prominence and user discoverability
    - Evaluate compliance with UK data protection requirements
    - Check for GDPR compliance indicators

    Return structured results with found policies, their accessibility status, and compliance assessment.
  "#
}

// BAML function for content relevance analysis
function AnalyzeContentRelevance(image: image, html_content: string?, url: string, context: string?) -> ContentRelevanceResult {
  client GPT4Vision
  prompt #"
    Analyze this website's content relevance to tax services and financial legitimacy.

    Website URL: {{ url }}
    {% if context %}
    Additional Context: {{ context }}
    {% endif %}

    RELEVANCE CATEGORIES TO ASSESS:

    1. **Tax Service Relevance**
       - Direct tax preparation services
       - Tax advice and consultation
       - HMRC-related services
       - Accounting and bookkeeping
       - Financial advisory services

    2. **Business Legitimacy Indicators**
       - Professional service descriptions
       - Qualified staff credentials
       - Client testimonials and reviews
       - Contact information completeness
       - Registration details (company numbers, etc.)

    3. **Service Quality Assessment**
       - Service offering clarity
       - Pricing transparency
       - Professional presentation
       - Trust indicators (certifications, associations)

    ANALYSIS CRITERIA:
    - HIGH relevance (0.8-1.0): Core tax/financial services
    - MEDIUM relevance (0.4-0.7): Related financial services
    - LOW relevance (0.0-0.3): Unrelated or unclear services

    For business legitimacy:
    - LEGITIMATE: Clear professional services with credentials
    - QUESTIONABLE: Some professional elements but concerns
    - SUSPICIOUS: Poor presentation or missing key information

    Return detailed assessment of content relevance and business legitimacy.
  "#
}

// BAML function for personal data analysis
function AnalyzePersonalDataRequests(image: image, html_content: string?, url: string) -> PersonalDataResult {
  client GPT4Vision
  prompt #"
    Analyze this website for personal data collection practices and GDPR compliance.

    Website URL: {{ url }}

    PERSONAL DATA ASSESSMENT CATEGORIES:

    1. **Data Collection Forms**
       - Contact forms requesting personal information
       - Registration/signup forms
       - Newsletter subscriptions
       - Service inquiry forms

    2. **Data Types Requested**
       - Basic personal info (name, email, phone)
       - Financial information (bank details, income)
       - Identity documents (passport, driving license)
       - Sensitive data (health, criminal records)

    3. **GDPR Compliance Indicators**
       - Explicit consent checkboxes
       - Clear data usage explanations
       - Right to withdraw consent
       - Data subject rights information
       - Cookie consent mechanisms

    4. **Inappropriate Data Requests**
       - Excessive personal information requests
       - Unnecessary sensitive data collection
       - Missing consent mechanisms
       - Unclear data usage purposes

    COMPLIANCE LEVELS:
    - COMPLIANT: Proper consent, clear purposes, appropriate data requests
    - PARTIALLY_COMPLIANT: Some good practices but missing elements
    - NON_COMPLIANT: Poor practices, excessive requests, missing consent

    Return comprehensive analysis of personal data practices and compliance status.
  "#
}

// BAML function for website completeness analysis
function AnalyzeWebsiteCompleteness(image: image, html_content: string?, url: string) -> WebsiteCompletenessResult {
  client GPT4Vision
  prompt #"
    Assess this website's completeness and professional presentation.

    Website URL: {{ url }}

    COMPLETENESS ASSESSMENT AREAS:

    1. **Essential Business Information**
       - Company name and description
       - Services/products offered
       - Contact information (address, phone, email)
       - Business registration details

    2. **Professional Presentation**
       - Design quality and consistency
       - Content organization and navigation
       - Image quality and relevance
       - Typography and readability

    3. **Functional Elements**
       - Navigation menu completeness
       - Working links and buttons
       - Form functionality
       - Mobile responsiveness indicators

    4. **Trust and Credibility**
       - About us/team information
       - Client testimonials or reviews
       - Professional certifications
       - Social media presence links

    5. **Completion Indicators**
       - Placeholder text or Lorem ipsum
       - Broken images or missing content
       - Under construction notices
       - Incomplete sections

    COMPLETENESS SCORES:
    - COMPLETE (0.8-1.0): Fully developed, professional website
    - MOSTLY_COMPLETE (0.6-0.7): Good development with minor gaps
    - PARTIALLY_COMPLETE (0.4-0.5): Basic structure but missing key elements
    - INCOMPLETE (0.0-0.3): Significant gaps or under development

    Return detailed assessment of website completeness and professionalism.
  "#
}

// BAML function for language analysis
function AnalyzeLanguageCapabilities(image: image, html_content: string?, url: string) -> LanguageAnalysisResult {
  client GPT4Vision
  prompt #"
    Analyze this website's language capabilities and internationalization features.

    Website URL: {{ url }}

    LANGUAGE ANALYSIS CATEGORIES:

    1. **Primary Language Detection**
       - Dominant language used on the website
       - Language quality and grammar assessment
       - Regional dialect or variant identification

    2. **Multi-language Support**
       - Language switcher presence
       - Available language options
       - Translation quality indicators
       - Localization features

    3. **Accessibility Features**
       - Language declaration in HTML
       - Text readability and clarity
       - Font support for different scripts
       - Right-to-left language support

    4. **International Compliance**
       - Currency display options
       - Date/time format variations
       - Address format considerations
       - Legal compliance across regions

    LANGUAGE SUPPORT LEVELS:
    - MULTILINGUAL: Full support for multiple languages
    - BILINGUAL: Support for two languages
    - MONOLINGUAL: Single language only
    - POOR_SUPPORT: Language issues or limited functionality

    QUALITY LEVELS:
    - PROFESSIONAL: High-quality, native-level content
    - GOOD: Generally good with minor issues
    - BASIC: Adequate but could be improved
    - POOR: Significant language or translation issues

    Return comprehensive language capabilities assessment.
  "#
}

// BAML function for workflow coordination
function CoordinateAnalysisWorkflow(url: string, context: string?, priorities: string[]) -> AnalysisOrchestrationResult {
  client GPT4Vision
  prompt #"
    Coordinate the analysis workflow for website compliance monitoring.

    Target URL: {{ url }}
    {% if context %}
    Analysis Context: {{ context }}
    {% endif %}
    {% if priorities %}
    Priority Areas: {{ priorities | join(", ") }}
    {% endif %}

    WORKFLOW COORDINATION OBJECTIVES:

    1. **Analysis Priority Assessment**
       - Determine which analysis components are most critical
       - Identify dependencies between analysis types
       - Assess resource requirements for each analysis

    2. **Risk-Based Scheduling**
       - High-risk indicators requiring immediate analysis
       - Medium-priority compliance checks
       - Comprehensive assessment requirements

    3. **Resource Optimization**
       - Parallel processing opportunities
       - Sequential dependency management
       - Timeout and retry strategies

    4. **Quality Assurance**
       - Cross-validation requirements
       - Confidence threshold management
       - Results consolidation strategy

    ANALYSIS TYPES TO COORDINATE:
    - Trademark violation detection
    - Policy compliance analysis
    - Content relevance assessment
    - Personal data practices review
    - Website completeness evaluation
    - Language capabilities analysis

    Return optimized workflow coordination plan with priorities and execution strategy.
  "#
}

// Enhanced data models
class PolicyLink {
  text string
  url string
  accessible bool
  found_method string
  location string?
}

class PolicyAnalysisResult {
  privacy_policy PolicyLink?
  terms_conditions PolicyLink?
  gdpr_compliance_indicators string[]
  accessibility_issues string[]
  compliance_score float
  recommendations string[]
}

enum RelevanceLevel {
  HIGH
  MEDIUM
  LOW
}

enum BusinessLegitimacy {
  LEGITIMATE
  QUESTIONABLE
  SUSPICIOUS
}

class ContentRelevanceResult {
  tax_service_relevance RelevanceLevel
  relevance_score float
  business_legitimacy BusinessLegitimacy
  legitimacy_score float
  service_categories string[]
  professional_indicators string[]
  concerns string[]
  recommendations string[]
}

enum ComplianceLevel {
  COMPLIANT
  PARTIALLY_COMPLIANT
  NON_COMPLIANT
}

enum DataSensitivity {
  BASIC
  FINANCIAL
  IDENTITY
  SENSITIVE
}

class DataRequest {
  data_type DataSensitivity
  purpose string
  consent_mechanism bool
  required bool
}

class PersonalDataResult {
  compliance_level ComplianceLevel
  compliance_score float
  data_requests DataRequest[]
  gdpr_indicators string[]
  privacy_concerns string[]
  recommendations string[]
}

enum CompletenessLevel {
  COMPLETE
  MOSTLY_COMPLETE
  PARTIALLY_COMPLETE
  INCOMPLETE
}

class WebsiteCompletenessResult {
  completeness_level CompletenessLevel
  completeness_score float
  missing_elements string[]
  professional_indicators string[]
  trust_factors string[]
  improvement_areas string[]
  recommendations string[]
}

enum LanguageSupport {
  MULTILINGUAL
  BILINGUAL
  MONOLINGUAL
  POOR_SUPPORT
}

enum LanguageQuality {
  PROFESSIONAL
  GOOD
  BASIC
  POOR
}

class LanguageAnalysisResult {
  primary_language string
  language_support LanguageSupport
  language_quality LanguageQuality
  quality_score float
  supported_languages string[]
  accessibility_features string[]
  internationalization_indicators string[]
  recommendations string[]
}

enum AnalysisPriority {
  CRITICAL
  HIGH
  MEDIUM
  LOW
}

class AnalysisTask {
  task_type string
  priority AnalysisPriority
  estimated_duration int
  dependencies string[]
  resource_requirements string[]
}

class AnalysisOrchestrationResult {
  recommended_sequence AnalysisTask[]
  parallel_processing_groups string[][]
  total_estimated_duration int
  risk_assessment string
  resource_allocation string[]
  quality_assurance_steps string[]
  recommendations string[]
}