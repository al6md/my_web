# Recommendation Verification System - Usage Guide

## Overview
This guide explains how to use the newly implemented verification system to audit your AI recommendation algorithms.

---

## 📊 Debug API Endpoints

### 1. Full Debug Report
```bash
GET /api/recommend/debug?user_id=<USER_ID>
```
Returns detailed breakdown of each algorithm stage with timing, results, and merge logic.

**Example:**
```bash
curl "http://localhost:5000/api/recommend/debug?user_id=1"
```

**Response includes:**
- `stages.transformer` — Embedding-based results
- `stages.neural` — Two-Tower model results
- `stages.behavioral` — View-based results
- `stages.collaborative_filtering` — CF results
- `hybrid_merge` — Weights and merged rankings
- `execution_summary` — Total timing and verification status

---

### 2. Health Check
```bash
GET /api/recommend/health
```
Quick status of pipeline components (embeddings, neural model, AI engine).

---

### 3. View Logs
```bash
GET /api/recommend/logs?lines=50
```
Retrieve recent recommendation pipeline logs.

---

## 🧪 Running Tests

### Unit Tests (pytest)
```bash
cd c:\Users\al6md\Desktop\project alham\flask_book_recommendation_starter
pytest tests/test_recommendation_pipeline.py -v
```

### Scenario Tests
```bash
python scripts/test_recommendation_scenarios.py
```

This script verifies:
- ✅ Algorithms return results (not empty)
- ✅ Multiple algorithms contribute to recommendations
- ✅ No static/fallback data is used

---

## 🏷️ Frontend Verification

On the Explore page, each recommended book displays:
- **Algorithm Badge** — Color indicates source:
  - 🟣 Purple: Transformer/Embeddings
  - 🔵 Blue: Neural Network (Two-Tower)
  - 🟢 Green: Hybrid
  - 🟠 Orange: Behavioral
  - 🔴 Rose: Collaborative Filtering
- **Confidence Score** — Neural match percentage
- **"How was this chosen?"** — Click for detailed explanation

---

## 📁 New Files Created

| File | Purpose |
|------|---------|
| `flask_book_recommendation/recommendation_logger.py` | Pipeline logging & tracing |
| `flask_book_recommendation/routes/debug_api.py` | Debug API endpoints |
| `tests/test_recommendation_pipeline.py` | Unit tests |
| `scripts/test_recommendation_scenarios.py` | End-to-end verification |

---

## 📝 Log Output Example

When recommendations are generated, logs appear in console and `logs/recommendations.log`:

```
═══════════════════════════════════════════════════════════
📊 RECOMMENDATION REQUEST: REQ-000001
   User ID: 42 | Time: 2026-02-02 01:15:00
───────────────────────────────────────────────────────────
   ├─ [TRANSFORMER]  Invoked: ✓ | Time: 45ms | Results: 15
   ├─ [NEURAL]       Invoked: ✓ | Time: 32ms | Results: 10
   ├─ [BEHAVIORAL]   Invoked: ✓ | Time: 18ms | Results: 8
   ├─ [HYBRID]       Merge: ✓  | Weights: T=0.25, N=0.35, B=0.25
───────────────────────────────────────────────────────────
   └─ [TOTAL] 95ms | Final Results: 24 books
═══════════════════════════════════════════════════════════
```
