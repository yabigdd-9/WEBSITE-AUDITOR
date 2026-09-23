# Build human identity review queue
# Queue of records that need human review for identity resolution.

class ReviewQueue:
    def __init__(self):
        self.queue = []  # list of records to review

    def add_to_queue(self, record, priority='normal'):
        """Add a record to the review queue."""
        self.queue.append({
            'record': record,
            'priority': priority,  # 'low', 'normal', 'high'
            'added_at': None,  # timestamp
            'reviewer': None,
            'status': 'pending'  # 'pending', 'in_review', 'resolved'
        })

    def get_next_record(self):
        """Get the next record to review (highest priority first)."""
        # Sort by priority: high > normal > low, then by order added
        priority_order = {'high': 0, 'normal': 1, 'low': 2}
        sorted_queue = sorted(self.queue, key=lambda x: (priority_order[x['priority']], self.queue.index(x)))
        for item in sorted_queue:
            if item['status'] == 'pending':
                return item
        return None

    def mark_as_reviewed(self, index, reviewer, decision):
        """Mark a record as reviewed."""
        if 0 <= index < len(self.queue):
            self.queue[index]['status'] = 'resolved'
            self.queue[index]['reviewer'] = reviewer
            self.queue[index]['decision'] = decision
            self.queue[index]['reviewed_at'] = None  # timestamp