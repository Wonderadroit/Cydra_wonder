"""Canonical causal verification bridge for persisted reasoning evidence."""
from __future__ import annotations

from .causal_verification import CausalVerificationResult, verify_persisted_causal_chain
from .system_model import SystemModel


def verify_causal_chain(model: SystemModel, chain_id: str) -> CausalVerificationResult:
    """Verify a persisted causal chain without executing or inventing evidence."""
    return verify_persisted_causal_chain(model, chain_id)
