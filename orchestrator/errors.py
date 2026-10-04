class OrchestrationError(Exception):
    """Expected operator or validation error."""


class ValidationError(OrchestrationError):
    """Input or artifact failed validation."""


class GateBlocked(OrchestrationError):
    """A required gate is not currently passed."""

