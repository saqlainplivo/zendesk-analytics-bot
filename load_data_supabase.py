#!/usr/bin/env python3
"""Load Zendesk CSV data into Supabase and generate embeddings.

Usage:
  python load_data_supabase.py            # normal: skip already-embedded tickets
  python load_data_supabase.py --reembed  # force re-embed all (use after schema change)
"""

import os
import sys
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv
import openai

load_dotenv()

FORCE_REEMBED = "--reembed" in sys.argv

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_ANON_KEY")
)
openai.api_key = os.getenv("OPENAI_API_KEY")

print("=" * 70)
print("Zendesk Analytics Bot - Data Loader")
if FORCE_REEMBED:
    print("  Mode: FORCE RE-EMBED (all tickets will be re-embedded)")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Load CSV
# ─────────────────────────────────────────────────────────────────────────────
print("\n📂 Step 1: Loading CSV data...")
csv_path = os.getenv("ZENDESK_CSV_PATH", "./Zendesk_tix.csv")

try:
    df = pd.read_csv(csv_path)
    print(f"✅ Loaded {len(df)} rows from {csv_path}")
except FileNotFoundError:
    print(f"❌ CSV file not found: {csv_path}")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Rename & clean columns
# ─────────────────────────────────────────────────────────────────────────────
print("\n🧹 Step 2: Cleaning data...")

df = df.rename(columns={
    "Id":                        "ticket_id",
    "Subject":                   "subject",
    "Organization":              "organization_name",
    "Requester":                 "requester_name",
    "Requester email":           "requester_email",
    "Priority":                  "priority",
    "Status":                    "status",
    "Ticket type":               "ticket_type",
    "Tags":                      "tags",
    "Created at":                "created_at",
    "Updated at":                "updated_at",
    "Assignee":                  "assignee",
    "Group":                     "group_name",
    "Solved at":                 "solved_at",
    "Resolution time":           "resolution_time",
    "Satisfaction Score":        "satisfaction_score",
    "Replies":                   "replies",
    "Product [list]":            "product",
    "Support Tier [list]":       "support_tier",
    "Shift [list]":              "shift",
    "Country [list]":            "country",
    "Carrier Ticket  [list]":    "carrier_ticket",
    "Customer Priority [list]":  "customer_priority",
    "Support Plan Type [list]":  "support_plan_type",
})

# Timestamps
for col in ["created_at", "updated_at", "solved_at"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce").apply(
            lambda x: x.isoformat() if pd.notna(x) else None
        )

# Tags → list
def parse_tags(val):
    if pd.isna(val) or not val:
        return []
    return [t.strip() for t in str(val).split() if t.strip()]

if "tags" in df.columns:
    df["tags"] = df["tags"].apply(parse_tags)

# Numeric columns
for col in ["resolution_time", "replies"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").apply(
            lambda x: int(x) if pd.notna(x) else None
        )

# Zendesk exports "-" for empty structured fields — treat as null
STRUCTURED_COLS = [
    "product", "ticket_type", "assignee", "group_name", "satisfaction_score",
    "support_tier", "shift", "country", "carrier_ticket",
    "customer_priority", "support_plan_type",
]
for col in STRUCTURED_COLS:
    if col in df.columns:
        df[col] = df[col].apply(
            lambda x: None if (pd.isna(x) or str(x).strip() == "-") else str(x).strip()
        )

# ticket_id must be string
df["ticket_id"] = df["ticket_id"].astype(str)

# All columns we want in Supabase (script safely skips any not present in CSV)
TICKET_COLS = [
    # Original 11 columns
    "ticket_id", "subject", "organization_name",
    "requester_name", "requester_email",
    "priority", "status", "tags",
    "created_at", "updated_at",
    # New columns — require ALTER TABLE migration in Supabase first
    "ticket_type", "product", "assignee", "group_name",
    "solved_at", "satisfaction_score", "resolution_time", "replies",
    "support_tier", "shift", "country", "carrier_ticket",
    "customer_priority", "support_plan_type",
]

df_clean = df[[c for c in TICKET_COLS if c in df.columns]].copy()
df_clean = df_clean.fillna({"organization_name": "Unknown", "priority": "Normal", "status": "open"})
df_clean = df_clean.where(pd.notna(df_clean), None)

records = df_clean.to_dict("records")
print(f"✅ Prepared {len(records)} ticket records  ({len(df_clean.columns)} columns each)")

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Upsert tickets into Supabase
# ─────────────────────────────────────────────────────────────────────────────
print("\n📤 Step 3: Uploading tickets to Supabase...")

BATCH_SIZE = 100
total_ok = 0
total_err = 0

for i in range(0, len(records), BATCH_SIZE):
    batch = records[i:i + BATCH_SIZE]
    try:
        supabase.table("tickets").upsert(batch).execute()
        total_ok += len(batch)
    except Exception as e:
        total_err += len(batch)
        print(f"  ⚠️  Batch {i // BATCH_SIZE + 1} error: {e}")

    if (i // BATCH_SIZE + 1) % 50 == 0 or i + BATCH_SIZE >= len(records):
        print(f"  Progress: {total_ok + total_err}/{len(records)} "
              f"({total_ok} ok, {total_err} errors)")

print(f"✅ Uploaded {total_ok} tickets ({total_err} errors)")

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Generate embeddings
# ─────────────────────────────────────────────────────────────────────────────
print("\n🤖 Step 4: Generating embeddings...")

PAGE_SIZE = 1000

# Fetch existing embedding ids (skip check if force reembed)
existing_ids = set()
if not FORCE_REEMBED:
    print("  Fetching existing embeddings...")
    page = 0
    while True:
        resp = (supabase.table("ticket_embeddings")
                .select("ticket_id")
                .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1)
                .execute())
        if not resp.data:
            break
        for row in resp.data:
            existing_ids.add(str(row["ticket_id"]))
        if len(resp.data) < PAGE_SIZE:
            break
        page += 1
    print(f"  {len(existing_ids)} already embedded")
else:
    print("  Skipping existing-embedding check (--reembed mode)")

# Fetch all tickets with the fields needed for rich embedding text
print("  Fetching tickets...")
all_tickets = []
page = 0
while True:
    resp = (supabase.table("tickets")
            .select("ticket_id,subject,product,ticket_type,tags,country,support_tier,organization_name")
            .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1)
            .execute())
    if not resp.data:
        break
    all_tickets.extend(resp.data)
    if len(resp.data) < PAGE_SIZE:
        break
    page += 1

to_embed = [t for t in all_tickets if str(t["ticket_id"]) not in existing_ids]
print(f"  {len(all_tickets)} total tickets, {len(to_embed)} need embedding")
print(f"  Estimated cost: ~${len(to_embed) * 0.00001:.2f}")

if not to_embed:
    print("  Nothing to embed — done.")
else:
    def make_embed_text(t: dict) -> str:
        """Build a rich embedding string from available ticket fields."""
        parts = [f"Subject: {t.get('subject') or ''}"]
        if t.get("product"):
            parts.append(f"Product: {t['product']}")
        if t.get("ticket_type"):
            parts.append(f"Type: {t['ticket_type']}")
        if t.get("country"):
            parts.append(f"Country: {t['country']}")
        if t.get("support_tier"):
            parts.append(f"Support Tier: {t['support_tier']}")
        tags = t.get("tags") or []
        if tags and isinstance(tags, list):
            parts.append(f"Tags: {' '.join(tags[:10])}")
        org = t.get("organization_name") or ""
        if org and org != "Unknown":
            parts.append(f"Organization: {org}")
        return "\n".join(parts)

    EMBED_BATCH = 100
    embedded_ok = 0
    embedded_err = 0

    for i in range(0, len(to_embed), EMBED_BATCH):
        batch = to_embed[i:i + EMBED_BATCH]
        texts = [make_embed_text(t) for t in batch]

        try:
            resp = openai.embeddings.create(model="text-embedding-3-small", input=texts)

            embed_rows = [
                {
                    "ticket_id": str(batch[j]["ticket_id"]),
                    "embedding": resp.data[j].embedding,
                    "content":   texts[j][:1000],
                }
                for j in range(len(batch))
            ]

            (supabase.table("ticket_embeddings")
             .upsert(embed_rows, on_conflict="ticket_id")
             .execute())

            embedded_ok += len(batch)

        except Exception as e:
            embedded_err += len(batch)
            print(f"  ⚠️  Embed batch {i // EMBED_BATCH + 1} error: {e}")

        if (i // EMBED_BATCH + 1) % 20 == 0 or i + EMBED_BATCH >= len(to_embed):
            done = i + len(batch)
            pct = done / len(to_embed) * 100 if to_embed else 100
            print(f"  Progress: {done}/{len(to_embed)} ({pct:.1f}%)")

    print(f"✅ Embedded {embedded_ok} tickets ({embedded_err} errors)")

print("\n" + "=" * 70)
print("✅ DATA LOADING COMPLETE!")
print("=" * 70)
print("\nStart the API:  uvicorn app.api.server:app --reload --port 8000")
print("=" * 70)
