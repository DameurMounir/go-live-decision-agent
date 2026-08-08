class GoLiveDecisionError(Exception):
    """Base error for controlled decision processing."""


class ValidationError(GoLiveDecisionError):
    """Raised when evidence, policy, or a decision packet is invalid."""


class SecurityBoundaryError(GoLiveDecisionError):
    """Raised when a path, identity, or authority boundary is violated."""


class ReviewConflictError(GoLiveDecisionError):
    """Raised for stale, replayed, expired, or conflicting human review."""
