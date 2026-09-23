# Add append-only review decisions
# Store review decisions in an append-only log.

class ReviewDecisionLog:
    def __init__(self):
        self.log = []  # list of decision entries

    def append_decision(self, record_id, decision, reviewer, notes=None):
        """Append a review decision to the log."""
        self.log.append({
            'record_id': record_id,
            'decision': decision,  # e.g., 'merge', 'separate', 'uncertain'
            'reviewer': reviewer,
            'timestamp': None,  # to be filled in
            'notes': notes
        })

    def get_decisions_for_record(self, record_id):
        """Get all decisions for a given record."""
        return [entry for entry in self.log if entry['record_id'] == record_id]

    def get_latest_decision(self, record_id):
        """Get the latest decision for a record."""
        decisions = self.get_decisions_for_record(record_id)
        if decisions:
            return decisions[-1]  # most recent
        return None