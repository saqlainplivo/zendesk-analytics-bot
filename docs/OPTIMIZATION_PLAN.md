# System Optimization Plan

## Current Issues Identified:

### 1. Performance Problems
- **List queries with organization**: Fetching ALL 29,000+ tickets for fuzzy matching
- Takes 15+ seconds per query
- Inefficient pagination (multiple database calls)

### 2. Filter Logic Issues
- Status filters not being applied correctly at SQL level
- Python-side filtering happening after fetching all data
- Filters being applied too aggressively or not at all

### 3. Intent Classification
- Some queries misclassified by reasoning engine
- Need better examples and clearer intent definitions

## Optimizations Implemented:

### ✅ Phase 1: Conditional Filter Application
- Filters now only apply when explicitly mentioned
- Prevents over-filtering of results
- More lenient matching for missing data

### ✅ Phase 2: SQL-Level Filtering
- Status filters applied directly in SQL query (when no org specified)
- Reduces data fetching significantly
- Faster response times

### ✅ Phase 3: Better Intent Examples
- Added more examples to Groq prompt
- Clearer intent definitions (list vs count vs search)
- Better organization extraction

## Remaining Optimizations Needed:

### 🔄 Phase 4: Optimize Organization Fuzzy Matching
**Problem**: Fetching all 29,000+ tickets for each organization query

**Solution Options**:
1. Use Supabase's `ilike` with proper escaping
2. Cache organization → tickets mapping
3. Use dedicated organization lookup table
4. Limit fetch to reasonable subset (1000-2000 tickets)

**Recommendation**: Option 4 (quick win) + Option 1 (proper fix)

### 🔄 Phase 5: Improve Count Query Routing
**Problem**: "Total tickets" queries failing

**Root Cause**: Need to investigate why count without filters returns None

**Solution**: Add better error handling and fallback logic

### 🔄 Phase 6: Cache Reasoning Results
**Problem**: Every query calls Groq API (adds 100-500ms)

**Solution**: Cache reasoning results for common query patterns

## Test Results Target:

**Current**: 54/80 (67.5%)
- Semantic: 10/10 (100%) ✓
- Time-based: 10/10 (100%) ✓
- Combined: 8/10 (80%) ✓
- Count: 4/10 (40%) ❌
- Status: 5/10 (50%) ❌
- Organization: 2/10 (20%) ❌

**Target After Optimizations**: 70-75/80 (87-94%)
- Count: 9/10 (90%) ← Fix SQL query issues
- Status: 8/10 (80%) ← Fix filter application
- Organization: 6/10 (60%) ← Optimize fuzzy matching
- All others: Maintain current high performance

## Implementation Priority:

1. **HIGH**: Fix count queries (4/10 → 9/10) - 5 queries
2. **HIGH**: Fix status queries (5/10 → 8/10) - 3 queries
3. **MEDIUM**: Improve organization (2/10 → 6/10) - 4 queries
4. **LOW**: Optimize performance (reduce 15s queries to <5s)

**Total Expected Gain**: +12-17 queries = 70-75/80 (87-94%)
