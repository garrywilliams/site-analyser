-- Migration: Add is_active column for selective processing
-- Run this if you have an existing site_analysis_data table without the is_active column

BEGIN;

-- Add the is_active column with default TRUE
ALTER TABLE site_analysis_data 
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

-- Set all existing records to active (if any exist)
UPDATE site_analysis_data 
SET is_active = TRUE 
WHERE is_active IS NULL;

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_site_analysis_is_active ON site_analysis_data (is_active);
CREATE INDEX IF NOT EXISTS idx_site_analysis_active_pending ON site_analysis_data (is_active, analysis_status);

-- Add comment for documentation
COMMENT ON COLUMN site_analysis_data.is_active IS 'Toggle for selective processing - only active records are analyzed by Agno agents';

COMMIT;