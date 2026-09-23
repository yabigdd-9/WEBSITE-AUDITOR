# Build conflict ledger
# Track conflicts between records that need human review.

class ConflictLedger:
    def __init__(self):
        self.conflicts = []  # list of conflict records

    def add_conflict(self, record1, record2, reason):
        """Add a conflict between two records."""
        self.conflicts.append({
            'record1': record1,
            'record2': record2,
            'reason': reason,
            'status': 'open'  # or 'resolved'
        })

    def get_open_conflicts(self):
        """Get all open conflicts."""
        return [c for c in self.conflicts if c['status'] == 'open']

    def resolve_conflict(self, index, resolution):
        """Mark a conflict as resolved."""
        if 0 <= index < len(self.conflicts):
            self.conflicts[index]['status'] = 'resolved'
            self.conflicts[index]['resolution'] = resolution