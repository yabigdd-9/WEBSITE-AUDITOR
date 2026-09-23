"""Before/After Proof + Automated Demo Generation.

P2-003 / v39: turns verified findings into reproducible visual proof packages.
Proof generation NEVER invents defects or declares its own fix successful —
it consumes verified findings, proposes corrected states, and an independent
verifier checks whether the original defect disappeared.
"""

from .schema import (
    AfterState,
    BeforeState,
    CaptureEnvironment,
    ProofPackage,
    ProposedFix,
    VerificationResult,
)

__all__ = [
    "BeforeState",
    "AfterState",
    "ProofPackage",
    "ProposedFix",
    "VerificationResult",
    "CaptureEnvironment",
]
