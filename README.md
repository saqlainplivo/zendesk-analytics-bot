# Zendesk Analytics Chatbot 🎯

Production-grade LLM-powered chatbot using **Supabase REST API** (works over HTTPS, bypasses firewall restrictions).

## Features

- **🤖 Hybrid Intelligence**: SQL analytics + RAG semantic search
- **🧠 Smart Router**: Auto-selects best agent for each query
- **📊 Evidence-Based**: All answers cite ticket IDs
- **☁️ Supabase REST API**: Works over HTTPS (port 443), bypasses firewall
- **🎨 Modern UI**: Clean, responsive web interface
- **⚡ Production-Ready**: FastAPI backend, modular architecture

## Quick Start

### 1. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your:
# - OPENAI_API_KEY
# - SUPABASE_URL
# - SUPABASE_ANON_KEY
```

### 3. Set Up Supabase RPC Function

**⚠️ Important:** Run this SQL in Supabase SQL Editor for vector search to work:

```sql
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

See `SUPABASE_SETUP.md` for detailed instructions.

### 4. Load Data (First Time Only)

```bash
python load_data_supabase.py
```

This will:
- Load 4,050 tickets from CSV
- Generate embeddings for all tickets
- Takes ~25 minutes, costs ~$0.04

### 5. Start the Server

```bash
./start.sh
# Or manually: uvicorn app.api.server:app --reload
```

Then open **http://localhost:8000** 🎉

## Architecture

```
CSV Data → ETL → Supabase (PostgreSQL + pgvector)
                      ↓
                Supabase REST API (HTTPS)
                      ↓
          ┌───────────┴───────────┐
          ↓                       ↓
    SQL Agent              RAG Agent
    (Analytics)         (Semantic Search)
          └───────── Router ──────┘
                      ↓
            FastAPI + Web UI
```

**Why Supabase REST API?**
- ✅ Works over HTTPS (port 443)
- ✅ Bypasses corporate firewall restrictions
- ✅ No PostgreSQL port access needed
- ✅ Same functionality as direct PostgreSQL

## Example Queries

Try these in the chat interface:

| Question | Agent | What It Does |
|----------|-------|--------------|
| "How many tickets from Kixie?" | 📊 SQL | Counts tickets filtered by organization |
| "What issues did Kixie face?" | 🔍 RAG | Semantic search for relevant tickets |
| "Top 5 customers by ticket count" | 📊 SQL | Aggregates and ranks organizations |
| "Summarize recent high-priority tickets" | 🔍 RAG | AI summary of relevant tickets |

## Project Structure

```
zendesk-analytics-bot/
├── app/
│   ├── api/
│   │   └── server.py              # FastAPI server
│   ├── agents/
│   │   ├── sql_agent_supabase.py  # SQL analytics via Supabase
│   │   ├── rag_agent_supabase.py  # Semantic search via Supabase
│   │   └── router_agent_supabase.py  # Smart routing
│   ├── database/
│   │   ├── supabase_db.py         # Supabase REST API wrapper
│   │   ├── schema.sql             # Database schema
│   │   └── vector_search_function.sql  # RPC function
│   ├── embeddings/
│   │   └── embedder.py            # OpenAI embeddings
│   ├── services/
│   │   └── analytics_service_supabase.py  # Business logic
│   ├── static/                    # Frontend (HTML/CSS/JS)
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── app.js
│   └── config.py                  # Configuration
├── load_data_supabase.py          # Data loader
├── start.sh                       # Easy startup script
├── SUPABASE_SETUP.md              # Detailed setup guide
├── requirements.txt
└── README.md
```

## Tech Stack

- **Backend**: FastAPI, Python 3.9+
- **Database**: Supabase (PostgreSQL + pgvector) via REST API
- **AI**: OpenAI (GPT-4, text-embedding-3-small)
- **Frontend**: Vanilla JavaScript, Modern CSS
- **Data**: Pandas for ETL

## API Endpoints

- `GET /` - Web UI (chat interface)
- `GET /health` - Health check
- `POST /chat` - Ask questions (main chatbot endpoint)
- `GET /tickets/{id}` - Get ticket details
- `GET /tickets` - List recent tickets
- `GET /stats` - Database statistics
- `GET /docs` - Interactive API documentation

## Environment Variables

```env
# Required
OPENAI_API_KEY=sk-proj-...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Optional (with defaults)
EMBEDDING_MODEL=text-embedding-3-small
LLM_MODEL=gpt-4-turbo-preview
TOP_K_RESULTS=5
SIMILARITY_THRESHOLD=0.7
```

## Troubleshooting

### "Database connection failed"
- ✅ **Fixed!** We now use Supabase REST API which works over HTTPS
- No PostgreSQL port access needed
- Works behind corporate firewalls

### "No relevant tickets found" for semantic queries
- Make sure you ran the SQL function in Supabase SQL Editor (see step 3)
- Check `SUPABASE_SETUP.md` for detailed instructions

### Slow responses
- First query may be slow (cold start)
- Subsequent queries are faster
- Consider using Supabase connection pooler for production

## Data

- **4,050 tickets** from Zendesk CSV export
- **100% embedding coverage** for semantic search
- Embeddings: 1,536 dimensions (text-embedding-3-small)

## Deployment

Deploy to cloud platforms:

**Railway:**
```bash
railway up
```

**Render:**
1. Connect your GitHub repo
2. Add environment variables
3. Deploy

**Docker:**
```bash
docker build -t zendesk-bot .
docker run -p 8000:8000 --env-file .env zendesk-bot
```

## License

MIT

---

Made with ❤️ using Claude Code
