-- Create RPC function for vector similarity search
-- Run this in Supabase SQL Editor

CREATE OR REPLACE FUNCTION match_tickets(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.7,
  match_count int DEFAULT 5
)
RETURNS TABLE (
  ticket_id varchar,
  subject text,
  description text,
  organization_name varchar,
  created_at timestamptz,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    t.ticket_id,
    t.subject,
    t.description,
    t.organization_name,
    t.created_at,
    1 - (te.embedding <=> query_embedding) as similarity
  FROM ticket_embeddings te
  JOIN tickets t ON t.ticket_id = te.ticket_id
  WHERE 1 - (te.embedding <=> query_embedding) > match_threshold
  ORDER BY te.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
