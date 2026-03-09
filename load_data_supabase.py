#!/usr/bin/env python3
"""Load Zendesk CSV data into Supabase and generate embeddings."""

import os
import sys
import pandas as pd
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv
import openai

load_dotenv()

# Initialize clients
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_ANON_KEY")
)
openai.api_key = os.getenv("OPENAI_API_KEY")

print("="*70)
print("Zendesk Analytics Bot - Data Loader")
print("="*70)

# Step 1: Load and clean CSV data
print("\n📂 Step 1: Loading CSV data...")
csv_path = os.getenv("ZENDESK_CSV_PATH", "../Zendesk_tix.csv")

try:
    df = pd.read_csv(csv_path)
    print(f"✅ Loaded {len(df)} rows from CSV")
except FileNotFoundError:
    print(f"❌ CSV file not found: {csv_path}")
    sys.exit(1)

# Clean and prepare data
print("\n🧹 Step 2: Cleaning data...")

# Normalize column names
df = df.rename(columns={
    "Id": "ticket_id",
    "Subject": "subject",
    "Description": "description",
    "Organization": "organization_name",
    "Requester": "requester_name",
    "Requester email": "requester_email",
    "Priority": "priority",
    "Status": "status",
    "Tags": "tags",
    "Created at": "created_at",
    "Updated at": "updated_at",
})

# Convert timestamps
df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce")

# Convert tags to array
def parse_tags(tags_value):
    if pd.isna(tags_value) or not tags_value:
        return []
    return [tag.strip() for tag in str(tags_value).split() if tag.strip()]

df["tags"] = df["tags"].apply(parse_tags)

# Convert to ISO format for Supabase
df["created_at"] = df["created_at"].apply(lambda x: x.isoformat() if pd.notna(x) else None)
df["updated_at"] = df["updated_at"].apply(lambda x: x.isoformat() if pd.notna(x) else None)

# Select relevant columns
columns = ["ticket_id", "subject", "description", "organization_name",
           "requester_name", "requester_email", "priority", "status",
           "tags", "created_at", "updated_at"]

df_clean = df[[col for col in columns if col in df.columns]].copy()

# Fill NaN values
df_clean = df_clean.fillna({
    "description": "",
    "organization_name": "Unknown",
    "priority": "Normal",
    "status": "open"
})

# Convert to records
records = df_clean.to_dict("records")
print(f"✅ Cleaned {len(records)} ticket records")

# Step 3: Insert into Supabase (in batches)
print("\n📤 Step 3: Uploading to Supabase...")

batch_size = 50
total_inserted = 0

for i in range(0, len(records), batch_size):
    batch = records[i:i + batch_size]
    try:
        result = supabase.table("tickets").upsert(batch).execute()
        total_inserted += len(batch)
        print(f"  Batch {i//batch_size + 1}: Inserted {len(batch)} tickets (total: {total_inserted})")
    except Exception as e:
        print(f"  ⚠️  Error in batch {i//batch_size + 1}: {e}")

print(f"✅ Uploaded {total_inserted} tickets to Supabase")

# Step 4: Generate embeddings
print("\n🤖 Step 4: Generating embeddings (this may take a few minutes)...")

# Fetch tickets from Supabase
tickets_response = supabase.table("tickets").select("ticket_id, subject, description").execute()
tickets = tickets_response.data

print(f"Found {len(tickets)} tickets to embed")

embedded_count = 0
print(f"⚠️  This will generate {len(tickets)} embeddings (costs ~${len(tickets) * 0.00001:.2f})")
print("Processing in batches...")

for idx, ticket in enumerate(tickets, 1):  # Process ALL tickets
    try:
        # Combine subject and description
        content = f"Subject: {ticket['subject']}\nDescription: {ticket.get('description') or ''}"

        # Generate embedding
        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=content[:8000]  # Limit text length
        )

        embedding = response.data[0].embedding

        # Store in Supabase
        supabase.table("ticket_embeddings").upsert({
            "ticket_id": ticket["ticket_id"],
            "embedding": embedding,
            "content": content[:1000]  # Store preview
        }).execute()

        embedded_count += 1
        if idx % 100 == 0:
            print(f"  Progress: {idx}/{len(tickets)} embeddings ({idx/len(tickets)*100:.1f}%)")

    except Exception as e:
        print(f"  ⚠️  Error embedding ticket {ticket['ticket_id']}: {e}")

print(f"✅ Generated {embedded_count} embeddings")

print("\n" + "="*70)
print("✅ DATA LOADING COMPLETE!")
print("="*70)
print("\nYou can now:")
print("1. Test the bot: python test_bot.py")
print("2. Start the API: uvicorn app.api.server:app --reload")
print("="*70)
