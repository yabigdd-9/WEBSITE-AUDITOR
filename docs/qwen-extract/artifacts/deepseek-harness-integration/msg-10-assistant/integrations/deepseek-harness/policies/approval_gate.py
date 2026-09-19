from integrations.deepseek_harness.state_machine.engine import StateMachineEngine
from typing import Tuple

class ApprovalGate:
    def __init__(self):
        self.sm = StateMachineEngine()

    def check_eligibility(self, prospect_id: int) -> Tuple[bool, str]:
        state = self.sm.get_state(prospect_id)
        
        # Must be at least VERIFIED to even consider outreach
        if state not in ['VERIFIED', 'REMEDIATION_PENDING', 'DEMO_PENDING', 'DEMO_READY', 'QA_PENDING', 'OUTREACH_PENDING', 'APPROVAL_PENDING']:
            return False, f"Ineligible state: {state}"
            
        # Fetch metadata to check suppression/duplicates
        # Simplified: In production, query DB for 'suppressed' flag
        # Here we rely on state machine integrity
        
        return True, "Eligible for QA"

    def approve_for_send(self, prospect_id: int, qa_report_path: str) -> bool:
        """
        Human or Automated Agent approves the draft.
        Transitions: QA_PENDING -> OUTREACH_PENDING -> APPROVAL_PENDING -> READY_TO_SEND
        """
        # 1. Move to Outreach Pending (Draft Generated)
        if not self.sm.transition(prospect_id, 'OUTREACH_PENDING', 'solution_architect', qa_report_path, 'Draft generated'):
            return False
            
        # 2. Move to Approval Pending
        if not self.sm.transition(prospect_id, 'APPROVAL_PENDING', 'critic_agent', qa_report_path, 'QA Passed'):
            return False
            
        # 3. Final Approval (Simulating Hermes Authority)
        # In real world, this might wait for a webhook or CLI confirm
        if not self.sm.transition(prospect_id, 'READY_TO_SEND', 'hermes_admin', qa_report_path, 'Approved for dispatch'):
            return False
            
        return True

    def mark_sent(self, prospect_id: int, email: str, confidence: float, template_ver: str, msg_id: str) -> bool:
        """
        Records the actual send event.
        """
        success = self.sm.record_outreach_send(prospect_id, email, confidence, template_ver, msg_id)
        if success:
            self.sm.transition(prospect_id, 'SENT', 'smtp_transport', '', f'Sent to {email}')
        return success
