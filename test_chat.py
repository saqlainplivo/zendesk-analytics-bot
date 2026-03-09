#!/usr/bin/env python3
"""Test the chatbot functionality."""

from app.database.supabase_db import SupabaseDB, check_db_connection
from app.services.analytics_service_supabase import AnalyticsService

print("=" * 70)
print("Zendesk Analytics Chatbot - Test Suite")
print("=" * 70)

# Test 1: Database connection
print("\n📊 Test 1: Database Connection")
if check_db_connection():
    print("✅ Supabase connected successfully")
else:
    print("❌ Supabase connection failed")
    exit(1)

# Test 2: SQL Analytics
print("\n📊 Test 2: SQL Analytics Agent")
service = AnalyticsService()
db = SupabaseDB()

test_queries = [
    "How many tickets are there?",
    "Top 5 customers by ticket count",
    "How many tickets from Kixie?",
]

for query in test_queries:
    print(f"\nQuery: '{query}'")
    try:
        result = service.answer_question(db, query)
        print(f"  Agent: {result['query_type']}")
        print(f"  Answer: {result['answer'][:100]}...")
        print(f"  Evidence: {len(result.get('evidence', []))} tickets")
        print("  ✅ Success")
    except Exception as e:
        print(f"  ❌ Error: {e}")

# Test 3: Semantic Search (RAG)
print("\n🔍 Test 3: Semantic Search Agent")
semantic_queries = [
    "What issues did companies face?",
]

for query in semantic_queries:
    print(f"\nQuery: '{query}'")
    try:
        result = service.answer_question(db, query)
        print(f"  Agent: {result['query_type']}")
        print(f"  Answer: {result['answer'][:100]}...")
        print(f"  Evidence: {len(result.get('evidence', []))} tickets")

        # Check if RPC function exists
        if not result.get('evidence'):
            print("  ⚠️  No evidence returned - you may need to run the SQL function")
            print("  See SUPABASE_SETUP.md for instructions")
        else:
            print("  ✅ Success")
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("\n" + "=" * 70)
print("Test Complete!")
print("=" * 70)
print("\nNext steps:")
print("1. If semantic search didn't work, run the SQL function in Supabase")
print("   (See SUPABASE_SETUP.md)")
print("2. Start the server: ./start.sh")
print("3. Open http://localhost:8000")
print("=" * 70)
