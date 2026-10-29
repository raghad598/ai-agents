-- applications.sql
-- Stores each job application the agent analyzes.
--
-- Unlike the resume tables, this one is written by the agent itself:
-- the Match Expert fills in match_score and gaps, and the Cover Letter
-- Expert fills in cover_letter. Nothing here is seeded from a CSV.
--
-- gaps is stored as a JSON list of requirement strings the resume
-- database had no good match for -- the part a generic AI writing tool
-- would quietly skip over.
CREATE TABLE IF NOT EXISTS applications (
    application_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    company         TEXT NOT NULL,
    role_title      TEXT NOT NULL,
    posting_text    TEXT NOT NULL,   -- the raw job posting as pasted
    match_score     REAL,            -- 0.0 to 100.0
    gaps            TEXT,            -- JSON list of unmatched requirements
    cover_letter    TEXT,
    created_at      TEXT NOT NULL    -- 'YYYY-MM-DD HH:MM:SS'
);