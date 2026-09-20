
"""
Portfolio DB: Replaces flat JSON with DuckDB for instant SQL querying across 1000s of sites.
Requires: pip install duckdb
"""
import json
from pathlib import Path

def init_portfolio_db(db_path="outputs/portfolio.duckdb"):
    try:
        import duckdb
    except ImportError:
        return {"status": "skipped", "reason": "duckdb not installed"}
        
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS site_health (
            domain VARCHAR, scan_date DATE, score INTEGER, 
            critical_issues INTEGER, cms VARCHAR, lcp_ms DOUBLE
        )
    """)
    con.close()
    return {"status": "initialized", "path": db_path}

def ingest_remediation_to_db(json_path, db_path="outputs/portfolio.duckdb"):
    try:
        import duckdb
    except ImportError: return
        
    data = json.loads(Path(json_path).read_text())
    domain = Path(json_path).stem.replace("-remediation", "")
    score = data.get("score", 0)
    issues = len(data.get("defects", data.get("issues", [])))
    
    con = duckdb.connect(db_path)
    con.execute("""
        INSERT INTO site_health (domain, scan_date, score, critical_issues, cms, lcp_ms) 
        VALUES (?, CURRENT_DATE, ?, ?, ?, ?)
    """, [domain, score, issues, "detected", None])
    con.close()
