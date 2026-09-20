"""Prometheus metrics export for the supervisor."""
from mm_pipeline import root

def export_prometheus_metrics(d) -> str:
    """Export metrics in Prometheus format."""
    lines = []
    
    # Pipeline items by state
    for row in d.execute('SELECT state, count(*) n FROM pipeline_items GROUP BY state'):
        lines.append(f'pipeline_items_total{{state="{row["state"]}"}} {row["n"]}')
    
    # Worker alive status
    for row in d.execute('SELECT worker_id, lease_seconds FROM worker_registry'):
        alive = 1  # simplified
        lines.append(f'worker_alive{{worker_id="{row["worker_id"]}"}} {alive}')
    
    # Lease statistics
    active = d.execute('SELECT count(*) FROM pipeline_items WHERE lease_until IS NOT NULL AND lease_until > ?', 
                       (datetime.now().isoformat(),)).fetchone()[0]
    lines.append(f'lease_active_total {active}')
    
    # Circuit breaker states
    for row in d.execute('SELECT service, state FROM circuit_breakers'):
        state_val = {'closed': 0, 'open': 1, 'half_open': 0.5}.get(row['state'], -1)
        lines.append(f'circuit_breaker_state{{service="{row[\"service\"]}",state="{row[\"state\"]}"}} {state_val}')
    
    # Rate bucket usage
    for row in d.execute('SELECT bucket, count, cap FROM rate_buckets'):
        lines.append(f'rate_bucket_usage{{bucket="{row[\"bucket\"]}",used="{row[\"count\"]}",cap="{row[\"cap\"]}"}} {row["count"]}')
    
    # Loop metrics
    for row in d.execute('SELECT name, value FROM mm_metrics'):
        lines.append(f'{row["name"]} {row["value"]}')

    return '\n'.join(lines) + '\n'

def export_prometheus_metrics_cli(d):
    print(export_prometheus_metrics(d))
