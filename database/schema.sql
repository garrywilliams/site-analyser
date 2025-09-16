-- Site Analysis Database Schema
-- Table to store scraped website data for compliance analysis

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS site_analysis_data (
    id SERIAL PRIMARY KEY,
    job_id UUID NOT NULL,
    
    -- URL and company information
    original_url TEXT NOT NULL,
    final_url TEXT, -- URL after redirects
    company_name TEXT, -- From original scraper data
    domain TEXT NOT NULL,
    
    -- Content data
    html_content TEXT,
    html_content_length INTEGER,
    screenshot_image BYTEA, -- Binary image data
    screenshot_hash VARCHAR(64) NOT NULL, -- SHA-256 hash of image
    
    -- Technical metadata
    load_time_ms INTEGER,
    redirected BOOLEAN DEFAULT FALSE,
    viewport_size VARCHAR(20), -- e.g., "1920x1080"
    screenshot_file_size INTEGER, -- bytes
    
    -- Processing status
    analysis_status VARCHAR(20) DEFAULT 'pending', -- pending, in_progress, completed, failed
    is_active BOOLEAN DEFAULT TRUE, -- Toggle for selective processing by Agno agents
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Original file references (for debugging)
    screenshot_filename TEXT,
    html_filename TEXT,
    
    -- Indexes for common queries
    CONSTRAINT unique_job_url UNIQUE (job_id, original_url)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_site_analysis_job_id ON site_analysis_data (job_id);
CREATE INDEX IF NOT EXISTS idx_site_analysis_domain ON site_analysis_data (domain);
CREATE INDEX IF NOT EXISTS idx_site_analysis_status ON site_analysis_data (analysis_status);
CREATE INDEX IF NOT EXISTS idx_site_analysis_is_active ON site_analysis_data (is_active);
CREATE INDEX IF NOT EXISTS idx_site_analysis_active_pending ON site_analysis_data (is_active, analysis_status);
CREATE INDEX IF NOT EXISTS idx_site_analysis_processed_at ON site_analysis_data (processed_at);
CREATE INDEX IF NOT EXISTS idx_site_analysis_screenshot_hash ON site_analysis_data (screenshot_hash);

-- Comments for documentation
COMMENT ON TABLE site_analysis_data IS 'Stores scraped website data for trademark and compliance analysis';
COMMENT ON COLUMN site_analysis_data.job_id IS 'UUID linking all resources from the same scraping run';
COMMENT ON COLUMN site_analysis_data.company_name IS 'Company name from original HMRC scraper data';
COMMENT ON COLUMN site_analysis_data.screenshot_hash IS 'SHA-256 hash of the screenshot image for deduplication';
COMMENT ON COLUMN site_analysis_data.analysis_status IS 'Status: pending, in_progress, completed, failed';
COMMENT ON COLUMN site_analysis_data.is_active IS 'Toggle for selective processing - only active records are analyzed by Agno agents';