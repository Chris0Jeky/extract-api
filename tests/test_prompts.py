"""The extraction system prompt restates the normalization contract per doc type."""

from llm.prompts import build_system_prompt


def test_invoice_prompt_states_the_normalization_contract():
    prompt = build_system_prompt("invoice")
    assert "an invoice" in prompt
    # The contract the strict schema enforces after parse must be stated up front.
    assert "ISO-8601" in prompt
    assert "minor units" in prompt
    assert "ISO-4217" in prompt
    assert "explicit null" in prompt


def test_job_posting_prompt_is_doc_type_specific():
    assert "a UK job posting" in build_system_prompt("uk_job_posting")


def test_unknown_doc_type_still_yields_a_usable_prompt():
    # The registry, not the prompt, authoritatively rejects an unsupported type, so
    # the prompt falls back to a generic label rather than failing.
    assert "a document" in build_system_prompt("passport")
