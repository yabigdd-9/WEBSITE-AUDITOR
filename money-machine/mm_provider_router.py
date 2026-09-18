"""Provider routing intelligence for Money Machine.

Automatically selects the cheapest suitable provider for each task type,
tracks costs and success rates, and falls back gracefully.

Routing rules:
- simple_html: Playwright (local, free)
- discovery: SearXNG (local, free)
- semantic_research: Exa (hosted, metered)
- difficult_js_or_crawl: Firecrawl (hosted, metered)
- provider_failure: fallback to next suitable provider
- credits_low: local_only_mode

All provider calls are logged to provider_usage for cost tracking.
"""
import os
import time
import json
import sqlite3
from pathlib import Path
from typing import Optional, Any

# Provider cost tracking (USD per 1k tokens or per call)
COSTS = {
    'playwright': 0.0,           # local
    'searxng': 0.0,              # local
    'exa': 0.005,                # per search (approx)
    'firecrawl': 0.002,          # per page (approx)
    'tavily': 0.001,             # per search (approx)
    'nous': 0.0,                 # free tier
    'openrouter': 0.0,           # free models
}

# Task type -> preferred provider chain
ROUTING = {
    'simple_html': ['playwright', 'exa', 'firecrawl'],
    'discovery': ['searxng', 'exa', 'tavily'],
    'semantic_research': ['exa', 'searxng', 'firecrawl'],
    'difficult_js': ['firecrawl', 'playwright', 'exa'],
    'full_site_crawl': ['firecrawl', 'exa'],
    'structured_extraction': ['exa', 'firecrawl'],
    'search': ['searxng', 'exa', 'tavily'],
    'extract': ['playwright', 'exa', 'firecrawl'],
    'research': ['exa', 'searxng', 'firecrawl'],
}

# Local-only mode threshold (USD remaining)
CREDITS_LOW_THRESHOLD = 0.50


def get_db():
    """Get Money Machine database connection."""
    from mm_core import connect
    return connect()


def log_usage(provider: str, call_type: str, cost: float = 0.0,
              tokens: int = 0, success: bool = True, db=None):
    """Log a provider call to provider_usage table."""
    if db is None:
        db = get_db()
    db.execute(
        'INSERT INTO provider_usage (provider, call_type, cost, tokens, success) '
        'VALUES (?, ?, ?, ?, ?)',
        (provider, call_type, cost, tokens, success)
    )
    db.commit()


def get_total_cost(db=None, hours: int = 24) -> float:
    """Get total cost in last N hours."""
    if db is None:
        db = get_db()
    row = db.execute(
        'SELECT COALESCE(SUM(cost), 0) FROM provider_usage '
        'WHERE called_at > datetime("now", ?)',
        (f'-{hours} hours',)
    ).fetchone()
    return row[0] if row else 0.0


def get_success_rate(provider: str, db=None, hours: int = 24) -> float:
    """Get success rate for a provider in last N hours."""
    if db is None:
        db = get_db()
    row = db.execute(
        'SELECT COUNT(*) as total, SUM(CASE WHEN success THEN 1 ELSE 0 END) as ok '
        'FROM provider_usage WHERE provider = ? AND called_at > datetime("now", ?)',
        (provider, f'-{hours} hours')
    ).fetchone()
    if not row or row['total'] == 0:
        return 1.0
    return row['ok'] / row['total']


def credits_low(db=None) -> bool:
    """Check if credits are running low."""
    return get_total_cost(db) > CREDITS_LOW_THRESHOLD


def select_provider(task_type: str, db=None) -> str:
    """Select the best provider for a task type.
    
    Considers:
    1. Task type routing chain
    2. Provider success rate
    3. Cost (local preferred)
    4. Credits remaining
    """
    if db is None:
        db = get_db()
    
    chain = ROUTING.get(task_type, ROUTING['extract'])
    
    # If credits are low, prefer local providers
    if credits_low(db):
        for p in chain:
            if COSTS.get(p, 0) == 0.0:
                return p
    
    # Otherwise, use first in chain with good success rate
    for provider in chain:
        rate = get_success_rate(provider, db)
        if rate >= 0.8:
            return provider
    
    # Fallback to first in chain
    return chain[0]


def record_result(provider: str, call_type: str, success: bool,
                 cost: float = 0.0, tokens: int = 0, db=None):
    """Record the result of a provider call."""
    log_usage(provider, call_type, cost, tokens, success, db)


def get_metrics(db=None) -> dict:
    """Get provider usage metrics for the last 24 hours."""
    if db is None:
        db = get_db()
    
    rows = db.execute(
        'SELECT provider, COUNT(*) as calls, SUM(cost) as total_cost, '
        'SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes '
        'FROM provider_usage WHERE called_at > datetime("now", "-24 hours") '
        'GROUP BY provider ORDER BY total_cost DESC'
    ).fetchall()
    
    metrics = {}
    for row in rows:
        metrics[row['provider']] = {
            'calls': row['calls'],
            'total_cost': row['total_cost'] or 0.0,
            'successes': row['successes'],
            'success_rate': row['successes'] / row['calls'] if row['calls'] > 0 else 0.0,
        }
    return metrics


def status_report() -> str:
    """Generate a human-readable status report."""
    db = get_db()
    cost_24h = get_total_cost(db, 24)
    cost_7d = get_total_cost(db, 168)
    metrics = get_metrics(db)
    
    lines = [
        "=== Provider Routing Status ===",
        f"Cost (24h): ${cost_24h:.4f}",
        f"Cost (7d):  ${cost_7d:.4f}",
        f"Credits low: {credits_low(db)}",
        "",
        "Provider metrics (24h):",
    ]
    
    for provider, m in metrics.items():
        lines.append(
            f"  {provider:15s} calls={m['calls']:3d}  "
            f"cost=${m['total_cost']:.4f}  "
            f"success={m['success_rate']:.0%}"
        )
    
    return '\n'.join(lines)
