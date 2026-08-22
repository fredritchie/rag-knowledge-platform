import pytest

from rag_platform.domain.state_machine import InvalidStatusTransition, ensure_transition
from rag_platform.domain.states import DocumentStatus


def test_phase1_happy_path_transitions_are_valid() -> None:
    ensure_transition(DocumentStatus.RECEIVED, DocumentStatus.PARSING)
    ensure_transition(DocumentStatus.PARSING, DocumentStatus.CHUNKING)
    ensure_transition(DocumentStatus.CHUNKING, DocumentStatus.VALIDATING)
    ensure_transition(DocumentStatus.VALIDATING, DocumentStatus.ACTIVE)


def test_invalid_transition_is_rejected() -> None:
    with pytest.raises(InvalidStatusTransition):
        ensure_transition(DocumentStatus.RECEIVED, DocumentStatus.ACTIVE)
