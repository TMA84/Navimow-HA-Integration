"""Tests for the NbEncryption request signing module."""

import hashlib
import hmac
import importlib.util
import sys

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Load the encryption module directly to avoid homeassistant dependency
_spec = importlib.util.spec_from_file_location(
    "encryption", "custom_components/navimow/encryption.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
NbEncryption = _mod.NbEncryption


class TestSignParams:
    """Tests for NbEncryption.sign_params."""

    def test_deterministic_output(self) -> None:
        """Identical inputs produce identical signatures."""
        params = {"device_sn": "ABC123", "action": "start"}
        token = "test_token_value"
        timestamp = 1700000000
        nonce = "a" * 32

        sig1 = NbEncryption.sign_params(params, token, timestamp, nonce)
        sig2 = NbEncryption.sign_params(params, token, timestamp, nonce)

        assert sig1 == sig2

    def test_signature_is_64_hex_chars(self) -> None:
        """HMAC-SHA256 produces a 64-character hex string."""
        params = {"key": "value"}
        sig = NbEncryption.sign_params(params, "token", 123, "nonce123")

        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_params_sorted_alphabetically(self) -> None:
        """Parameters are sorted by key before signing."""
        params_a = {"zebra": "1", "alpha": "2"}
        params_b = {"alpha": "2", "zebra": "1"}
        token = "token"
        timestamp = 100
        nonce = "nonce"

        sig_a = NbEncryption.sign_params(params_a, token, timestamp, nonce)
        sig_b = NbEncryption.sign_params(params_b, token, timestamp, nonce)

        assert sig_a == sig_b

    def test_different_params_produce_different_signatures(self) -> None:
        """Different parameters produce different signatures."""
        token = "token"
        timestamp = 100
        nonce = "nonce"

        sig1 = NbEncryption.sign_params({"a": "1"}, token, timestamp, nonce)
        sig2 = NbEncryption.sign_params({"a": "2"}, token, timestamp, nonce)

        assert sig1 != sig2

    def test_different_tokens_produce_different_signatures(self) -> None:
        """Different access tokens produce different signatures."""
        params = {"key": "value"}
        timestamp = 100
        nonce = "nonce"

        sig1 = NbEncryption.sign_params(params, "token_a", timestamp, nonce)
        sig2 = NbEncryption.sign_params(params, "token_b", timestamp, nonce)

        assert sig1 != sig2

    def test_empty_params(self) -> None:
        """Empty params dict still produces a valid signature."""
        sig = NbEncryption.sign_params({}, "token", 100, "nonce")

        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_signature_matches_manual_computation(self) -> None:
        """Signature matches a manually computed HMAC-SHA256."""
        params = {"b": "2", "a": "1"}
        token = "secret_key"
        timestamp = 1234567890
        nonce = "deadbeef" * 4

        # Manual computation
        sorted_str = "a=1&b=2"
        string_to_sign = f"{sorted_str}{timestamp}{nonce}"
        expected = hmac.new(
            key=token.encode("utf-8"),
            msg=string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        actual = NbEncryption.sign_params(params, token, timestamp, nonce)
        assert actual == expected


class TestGenerateNonce:
    """Tests for NbEncryption.generate_nonce."""

    def test_nonce_length(self) -> None:
        """Nonce is exactly 32 characters."""
        nonce = NbEncryption.generate_nonce()
        assert len(nonce) == 32

    def test_nonce_is_hex(self) -> None:
        """Nonce contains only hex characters."""
        nonce = NbEncryption.generate_nonce()
        assert all(c in "0123456789abcdef" for c in nonce)

    def test_nonces_are_unique(self) -> None:
        """Successive nonces are different (with overwhelming probability)."""
        nonces = {NbEncryption.generate_nonce() for _ in range(100)}
        assert len(nonces) == 100


class TestBuildSignedHeaders:
    """Tests for NbEncryption.build_signed_headers."""

    def test_contains_all_required_keys(self) -> None:
        """Headers contain all required fields."""
        headers = NbEncryption.build_signed_headers(
            access_token="tok",
            signature="sig",
            timestamp=123,
            nonce="nonce",
        )

        assert "Authorization" in headers
        assert "appfrom" in headers
        assert "appbrand" in headers
        assert "x-nonce" in headers
        assert "x-timestamp" in headers
        assert "x-signature" in headers

    def test_authorization_bearer_format(self) -> None:
        """Authorization header uses Bearer token format."""
        headers = NbEncryption.build_signed_headers(
            access_token="my_token",
            signature="sig",
            timestamp=123,
            nonce="nonce",
        )

        assert headers["Authorization"] == "Bearer my_token"

    def test_appfrom_is_navimow(self) -> None:
        """appfrom header is always 'navimow'."""
        headers = NbEncryption.build_signed_headers("t", "s", 0, "n")
        assert headers["appfrom"] == "navimow"

    def test_appbrand_is_android(self) -> None:
        """appbrand header is always 'Android'."""
        headers = NbEncryption.build_signed_headers("t", "s", 0, "n")
        assert headers["appbrand"] == "Android"

    def test_timestamp_as_string(self) -> None:
        """x-timestamp is the timestamp converted to string."""
        headers = NbEncryption.build_signed_headers("t", "s", 9876543210, "n")
        assert headers["x-timestamp"] == "9876543210"

    def test_nonce_passed_through(self) -> None:
        """x-nonce is the nonce value passed in."""
        headers = NbEncryption.build_signed_headers("t", "s", 0, "abc123")
        assert headers["x-nonce"] == "abc123"

    def test_signature_passed_through(self) -> None:
        """x-signature is the signature value passed in."""
        headers = NbEncryption.build_signed_headers("t", "my_sig", 0, "n")
        assert headers["x-signature"] == "my_sig"


# Feature: navimow-home-assistant, Property 2: Request Signing Determinism
class TestRequestSigningDeterminismProperty:
    """Property-based tests for request signing determinism.

    **Validates: Requirements 1.6**
    """

    @given(
        params=st.dictionaries(st.text(), st.text()),
        access_token=st.text(min_size=1),
        timestamp=st.integers(min_value=0, max_value=2**53),
        nonce=st.text(min_size=1),
    )
    @settings(max_examples=100)
    def test_sign_params_deterministic(
        self,
        params: dict[str, str],
        access_token: str,
        timestamp: int,
        nonce: str,
    ) -> None:
        """For any valid inputs, calling sign_params twice produces identical output.

        **Validates: Requirements 1.6**
        """
        sig1 = NbEncryption.sign_params(params, access_token, timestamp, nonce)
        sig2 = NbEncryption.sign_params(params, access_token, timestamp, nonce)

        assert sig1 == sig2
        # Verify signature is always a valid 64-char hex string
        assert len(sig1) == 64
        assert all(c in "0123456789abcdef" for c in sig1)

    @given(
        access_token=st.text(min_size=1),
        signature=st.text(),
        timestamp=st.integers(min_value=0, max_value=2**53),
        nonce=st.text(),
    )
    @settings(max_examples=100)
    def test_signed_headers_always_contain_app_identifiers(
        self,
        access_token: str,
        signature: str,
        timestamp: int,
        nonce: str,
    ) -> None:
        """Signed headers always contain appfrom=navimow and appbrand=Android.

        **Validates: Requirements 1.6**
        """
        headers = NbEncryption.build_signed_headers(
            access_token=access_token,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )

        assert headers["appfrom"] == "navimow"
        assert headers["appbrand"] == "Android"
