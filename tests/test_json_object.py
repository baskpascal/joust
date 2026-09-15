"""A model's answer either contains a JSON object, or it does not.

That distinction has to survive as a typed code, not just a message: an
operator reading a mission's boundary needs to be able to tell "the text had
no JSON at all" (MODEL_RESPONSE_INVALID) apart from every other reason an
answer got rejected.
"""

import pytest

from hackathon_competitor.ai import ModelResponseInvalid, json_object


def test_a_clean_json_object_is_returned():
    assert json_object('{"a": 1}') == {"a": 1}


def test_json_embedded_in_surrounding_text_is_still_found():
    assert json_object('Here is the answer: {"a": 1} - done') == {"a": 1}


def test_text_with_no_json_object_raises_a_typed_model_response_invalid():
    with pytest.raises(ModelResponseInvalid) as excinfo:
        json_object("I cannot help with that request.")

    assert excinfo.value.code == "MODEL_RESPONSE_INVALID"


def test_model_response_invalid_is_still_a_value_error():
    """Existing `except ValueError` handling must keep catching this."""

    assert issubclass(ModelResponseInvalid, ValueError)
