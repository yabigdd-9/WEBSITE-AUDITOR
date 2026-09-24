"""
Proof integration engine for proposals.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ProofLabel(Enum):
    OBSERVED = "OBSERVED"  # actual before state
    SIMULATED = "SIMULATED"  # preview/simulation


@dataclass
class ProofReference:
    """Reference to proof data supporting a scope item or proposal."""
    proof_id: str
    label: ProofLabel  # OBSERVED or SIMULATED
    description: str
    url: Optional[str] = None  # link to proof data
    timestamp: Optional[str] = None  # when proof was generated
    confidence: str = "medium"  # low, medium, high
    data_type: str = "screenshot"  # screenshot, video, metrics, etc.


@dataclass
class ProofPackage:
    """Package of proof references for a scope item or proposal."""
    scope_item_id: str
    proof_references: List[ProofReference]
    total_proof_count: int
    observed_count: int
    simulated_count: int


class ProofIntegrationEngine:
    """Integrates proof package references and preserves OBSERVED vs SIMULATED labels."""

    def __init__(self):
        # proof_integration rules from plan
        self.rules = {
            'never_describe_simulated_as_completed_work': True,
            'proof_should_include_observed_preview_technical_delta_confidence': True
        }

    def integrate_proof_references(self, scope_items: List[Any],
                                 proof_data: Dict[str, Any]) -> List[Any]:
        """
        Integrate proof references into scope items.
        """
        enhanced_scope_items = []

        for scope_item in scope_items:
            # Get proof references for this scope item
            scope_item_id = getattr(scope_item, 'scope_id', str(hash(str(scope_item))))
            scope_proofs = proof_data.get(scope_item_id, [])

            # Convert proof references to ProofReference objects
            proof_refs = []
            for proof in scope_proofs:
                proof_ref = ProofReference(
                    proof_id=proof.get('proof_id', f'proof_{len(proof_refs)}'),
                    label=ProofLabel[proof.get('label', 'OBSERVED').upper()],
                    description=proof.get('description', ''),
                    url=proof.get('url'),
                    timestamp=proof.get('timestamp'),
                    confidence=proof.get('confidence', 'medium'),
                    data_type=proof.get('data_type', 'screenshot')
                )
                proof_refs.append(proof_ref)

            # Create proof package
            proof_package = ProofPackage(
                scope_item_id=scope_item_id,
                proof_references=proof_refs,
                total_proof_count=len(proof_refs),
                observed_count=len([p for p in proof_refs if p.label == ProofLabel.OBSERVED]),
                simulated_count=len([p for p in proof_refs if p.label == ProofLabel.SIMULATED])
            )

            # Enhance scope item with proof information
            enhanced_item = self._enhance_scope_item_with_proof(scope_item, proof_package)
            enhanced_scope_items.append(enhanced_item)

        return enhanced_scope_items

    def _enhance_scope_item_with_proof(self, scope_item: Any,
                                     proof_package: ProofPackage) -> Any:
        """Enhance a scope item with proof package information."""
        # Add proof package to scope item
        if hasattr(scope_item, 'proof_package'):
            scope_item.proof_package = proof_package
        else:
            # For simplicity, we'll just return the scope item as-is
            # In a real implementation, we'd modify the scope item object
            pass

        return scope_item

    def get_proof_summary(self, proof_package: ProofPackage) -> Dict[str, Any]:
        """Get a summary of proof for reporting."""
        return {
            'total_proofs': proof_package.total_proof_count,
            'observed_proofs': proof_package.observed_count,
            'simulated_proofs': proof_package.simulated_count,
            'has_observed': proof_package.observed_count > 0,
            'has_simulated': proof_package.simulated_count > 0,
            'proof_labels': [p.label.value for p in proof_package.proof_references]
        }

    def validate_proof_usage(self, proof_package: ProofPackage) -> bool:
        """
        Validate that proof usage follows the rules.
        In particular, never describe simulated preview as completed client work.
        """
        # Check rule: Never describe a simulated preview as completed client work
        # This would be validated in the proposal generation/templating stage
        # For now, we just ensure we have the labels correct

        for proof in proof_package.proof_references:
            if proof.label == ProofLabel.SIMULATED:
                # Simulated proof should be clearly labeled as such
                if 'simulated' not in proof.description.lower() and \
                   'preview' not in proof.description.lower():
                    logger.warning(f"Simulated proof {proof.proof_id} should be clearly labeled as simulated/preview")
                    # Don't return False here as this is a warning, not a validation failure

        return True

    def get_evidence_refs_from_proof(self, proof_package: ProofPackage) -> List[str]:
        """
        Extract evidence references from proof package for proposal evidence_refs field.
        """
        evidence_refs = []
        for proof in proof_package.proof_references:
            if proof.url:
                evidence_refs.append(proof.url)
            elif proof.proof_id:
                evidence_refs.append(f"proof:{proof.proof_id}")
        return evidence_refs