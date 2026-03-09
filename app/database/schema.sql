-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop existing tables if they exist
DROP TABLE IF EXISTS ticket_embeddings CASCADE;
DROP TABLE IF EXISTS comments CASCADE;
DROP TABLE IF EXISTS tickets CASCADE;

-- Tickets table
CREATE TABLE tickets (
    ticket_id VARCHAR(50) PRIMARY KEY,
    subject TEXT NOT NULL,
    description TEXT,
    organization_name VARCHAR(255),
    requester_name VARCHAR(255),
    requester_email VARCHAR(255),
    requester_domain VARCHAR(255),
    assignee VARCHAR(255),
    assignee_email VARCHAR(255),
    priority VARCHAR(50),
    status VARCHAR(50),
    ticket_type VARCHAR(50),
    group_name VARCHAR(255),
    tags TEXT[],
    product VARCHAR(100),
    issue_type VARCHAR(100),
    region VARCHAR(100),
    country VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE,
    solved_at TIMESTAMP WITH TIME ZONE,
    via_channel VARCHAR(50),
    satisfaction_score VARCHAR(50),
    created_date DATE GENERATED ALWAYS AS (created_at::DATE) STORED,
    INDEX idx_tickets_org (organization_name),
    INDEX idx_tickets_created_at (created_at),
    INDEX idx_tickets_priority (priority),
    INDEX idx_tickets_status (status),
    INDEX idx_tickets_created_date (created_date),
    INDEX idx_tickets_tags (tags) USING GIN
);

-- Comments table
CREATE TABLE comments (
    comment_id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(50) NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    author VARCHAR(255),
    author_email VARCHAR(255),
    body TEXT,
    is_public BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    INDEX idx_comments_ticket (ticket_id),
    INDEX idx_comments_created_at (created_at)
);

-- Ticket embeddings table (for semantic search)
CREATE TABLE ticket_embeddings (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(50) NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    embedding vector(1536) NOT NULL,
    content TEXT NOT NULL,
    embedding_model VARCHAR(100) NOT NULL DEFAULT 'text-embedding-3-small',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(ticket_id)
);

-- Create index for vector similarity search using cosine distance
CREATE INDEX idx_ticket_embeddings_vector
ON ticket_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for quick ticket lookup
CREATE INDEX idx_ticket_embeddings_ticket_id ON ticket_embeddings(ticket_id);

-- Create view for common analytics queries
CREATE OR REPLACE VIEW ticket_analytics AS
SELECT
    ticket_id,
    subject,
    organization_name,
    priority,
    status,
    created_at,
    created_date,
    DATE_TRUNC('month', created_at) as created_month,
    DATE_TRUNC('week', created_at) as created_week,
    tags,
    issue_type,
    region
FROM tickets;

-- Function to search tickets by semantic similarity
CREATE OR REPLACE FUNCTION search_tickets_by_embedding(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    ticket_id VARCHAR(50),
    subject TEXT,
    content TEXT,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.ticket_id,
        t.subject,
        te.content,
        1 - (te.embedding <=> query_embedding) as similarity
    FROM ticket_embeddings te
    JOIN tickets t ON t.ticket_id = te.ticket_id
    WHERE 1 - (te.embedding <=> query_embedding) > match_threshold
    ORDER BY te.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Grant permissions (adjust as needed for your setup)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_user;
