# Supabase Setup for Vector Search

The chatbot needs one RPC function in Supabase for vector similarity search.

## Setup Steps

1. **Go to Supabase SQL Editor:**
   - Open your Supabase project: https://gisjhemvtsetpjuizdfh.supabase.co
   - Click on "SQL Editor" in the left sidebar
   - Click "New query"

2. **Copy and run this SQL:**

```sql
-- Create RPC function for vector similarity search
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
```

3. **Click "Run" (or press Cmd/Ctrl + Enter)**

4. **Verify:**
   - You should see "Success. No rows returned"
   - The function is now ready to use!

## What This Does

This function enables semantic search by:
- Taking a query embedding (vector of numbers)
- Finding the most similar ticket embeddings using cosine similarity
- Joining with ticket data to return full ticket information
- Filtering by similarity threshold
- Returning top N most similar tickets

## Troubleshooting

If you get an error:
- Make sure pgvector extension is enabled (should be from schema setup)
- Check that ticket_embeddings table exists
- Verify embeddings column is type `vector(1536)`

That's it! Your chatbot will now work with full semantic search capabilities.
