"""Tests for the Navimow authentication module (OAuth2 Bearer token)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

# Mock homeassistant modules so the package __init__.py can be imported
_ha_mock = ModuleType("homeassistant")
_ha_mock.config_entries = ModuleType("homeassistant.config_entries")
_ha_mock.config_entries.ConfigEntry = MagicMock
_ha_mock.core = ModuleType("homeassistant.core")
_ha_mock.core.HomeAssistant = MagicMock
sys.modules.setdefault("homeassistant", _ha_mock)
sys.modules.setdefault("homeassistant.config_entries", _ha_mock.config_entries)
sys.modules.setdefault("homeassistant.core", _ha_mock.core)

from custom_components.navimow.auth import NavimowAuth, NavimowAuthError


@pytest.fixture
def token_refresh_callback() -> AsyncMock:
    """Return a mock token refresh callback."""
    return AsyncMock()


@pytest.fixture
def valid_token_expiry() -> datetime:
    """Return a token expiry time in the future."""
    return datetime.now(timezone.utc) + timedelta(hours=1)


@pytest.fixture
def expired_token_expiry() -> datetime:
    """Return a token expiry time in the past."""
    return datetime.now(timezone.utc) - timedelta(hours=1)


@pytest.fixture
def auth_instance(mock_session, token_refresh_callback, valid_token_expiry) -> NavimowAuth:
    """Return a NavimowAuth instance with valid tokens."""
    return NavimowAuth(
        session=mock_session,
        region="fra",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_expiry=valid_token_expiry,
        on_token_refresh=token_refresh_callback,
    )


@pytest.fixture
def expired_auth_instance(mock_session, token_refresh_callback, expired_token_expiry) -> NavimowAuth:
    """Return a NavimowAuth instance with expired tokens."""
    # Set up the mock session to return a valid refresh response
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(return_value={
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 7200,
    })
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(return_value=response)

    return NavimowAuth(
        session=mock_session,
        region="fra",
        access_token="expired_access_token",
        refresh_token="test_refresh_token",
        token_expiry=expired_token_expiry,
        on_token_refresh=token_refresh_callback,
    )


class TestPassportUrl:
    """Tests for passport URL construction."""

    def test_passport_url_fra(self, mock_session, token_refresh_callback, valid_token_expiry):
        """Test passport URL for fra region."""
        auth = NavimowAuth(
            session=mock_session,
            region="fra",
            access_token="token",
            refresh_token="refresh",
            token_expiry=valid_token_expiry,
            on_token_refresh=token_refresh_callback,
        )
        assert auth.passport_url == "https://api-passport-fra.ninebot.com/"

    def test_passport_url_ore(self, mock_session, token_refresh_callback, valid_token_expiry):
        """Test passport URL for ore region."""
        auth = NavimowAuth(
            session=mock_session,
            region="ore",
            access_token="token",
            refresh_token="refresh",
            token_expiry=valid_token_expiry,
            on_token_refresh=token_refresh_callback,
        )
        assert auth.passport_url == "https://api-passport-ore.ninebot.com/"

    def test_passport_url_sg(self, mock_session, token_refresh_callback, valid_token_expiry):
        """Test passport URL for sg region."""
        auth = NavimowAuth(
            session=mock_session,
            region="sg",
            access_token="token",
            refresh_token="refresh",
            token_expiry=valid_token_expiry,
            on_token_refresh=token_refresh_callback,
        )
        assert auth.passport_url == "https://api-passport-sg.ninebot.com/"


class TestAsyncGetAccessToken:
    """Tests for async_get_access_token."""

    @pytest.mark.asyncio
    async def test_returns_token_when_not_expired(self, auth_instance):
        """Test that a valid token is returned directly without refresh."""
        token = await auth_instance.async_get_access_token()
        assert token == "test_access_token"

    @pytest.mark.asyncio
    async def test_refreshes_when_expired(self, expired_auth_instance, token_refresh_callback):
        """Test that an expired token triggers refresh."""
        token = await expired_auth_instance.async_get_access_token()
        assert token == "new_access_token"
        token_refresh_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_refreshes_when_about_to_expire(self, mock_session, token_refresh_callback):
        """Test that a token about to expire (within 60s) triggers refresh."""
        # Token expires in 30 seconds (within the 60s buffer)
        near_expiry = datetime.now(timezone.utc) + timedelta(seconds=30)

        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value={
            "access_token": "refreshed_token",
            "refresh_token": "refreshed_refresh",
            "expires_in": 3600,
        })
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=response)

        auth = NavimowAuth(
            session=mock_session,
            region="fra",
            access_token="about_to_expire_token",
            refresh_token="refresh",
            token_expiry=near_expiry,
            on_token_refresh=token_refresh_callback,
        )

        token = await auth.async_get_access_token()
        assert token == "refreshed_token"
        token_refresh_callback.assert_called_once()


class TestAsyncRefreshToken:
    """Tests for async_refresh_token."""

    @pytest.mark.asyncio
    async def test_successful_refresh(self, mock_session, token_refresh_callback, valid_token_expiry):
        """Test successful token refresh."""
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value={
            "access_token": "refreshed_token",
            "refresh_token": "refreshed_refresh",
            "expires_in": 3600,
        })
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=response)

        auth = NavimowAuth(
            session=mock_session,
            region="fra",
            access_token="old_token",
            refresh_token="old_refresh",
            token_expiry=valid_token_expiry,
            on_token_refresh=token_refresh_callback,
        )

        access, refresh, expiry = await auth.async_refresh_token()

        assert access == "refreshed_token"
        assert refresh == "refreshed_refresh"
        assert expiry > datetime.now(timezone.utc)
        token_refresh_callback.assert_called_once_with(
            "refreshed_token", "refreshed_refresh", expiry
        )

    @pytest.mark.asyncio
    async def test_refresh_failure_raises_error(self, mock_session, token_refresh_callback, valid_token_expiry):
        """Test that a failed refresh raises NavimowAuthError."""
        response = AsyncMock()
        response.status = 401
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=response)

        auth = NavimowAuth(
            session=mock_session,
            region="fra",
            access_token="old_token",
            refresh_token="invalid_refresh",
            token_expiry=valid_token_expiry,
            on_token_refresh=token_refresh_callback,
        )

        with pytest.raises(NavimowAuthError, match="Token refresh failed with status 401"):
            await auth.async_refresh_token()

    @pytest.mark.asyncio
    async def test_refresh_missing_access_token_raises_error(
        self, mock_session, token_refresh_callback, valid_token_expiry
    ):
        """Test that a response without access_token raises error."""
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value={"error": "invalid_grant"})
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=response)

        auth = NavimowAuth(
            session=mock_session,
            region="fra",
            access_token="old_token",
            refresh_token="old_refresh",
            token_expiry=valid_token_expiry,
            on_token_refresh=token_refresh_callback,
        )

        with pytest.raises(NavimowAuthError, match="missing access_token"):
            await auth.async_refresh_token()

    @pytest.mark.asyncio
    async def test_refresh_preserves_refresh_token_if_not_returned(
        self, mock_session, token_refresh_callback, valid_token_expiry
    ):
        """Test that the old refresh token is kept if not in response."""
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value={
            "access_token": "new_access",
            "expires_in": 3600,
        })
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=response)

        auth = NavimowAuth(
            session=mock_session,
            region="fra",
            access_token="old_token",
            refresh_token="keep_this_refresh",
            token_expiry=valid_token_expiry,
            on_token_refresh=token_refresh_callback,
        )

        access, refresh, expiry = await auth.async_refresh_token()
        assert access == "new_access"
        assert refresh == "keep_this_refresh"


class TestGetAuthHeaders:
    """Tests for get_auth_headers (Bearer token + requestId)."""

    def test_get_auth_headers_contains_bearer(self, auth_instance):
        """Test that get_auth_headers returns Bearer token header."""
        headers = auth_instance.get_auth_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test_access_token"

    def test_get_auth_headers_contains_request_id(self, auth_instance):
        """Test that get_auth_headers returns a requestId header."""
        headers = auth_instance.get_auth_headers()

        assert "requestId" in headers
        # requestId should be a UUID string
        assert len(headers["requestId"]) > 0

    def test_get_auth_headers_unique_request_ids(self, auth_instance):
        """Test that each call generates a unique requestId."""
        headers1 = auth_instance.get_auth_headers()
        headers2 = auth_instance.get_auth_headers()

        assert headers1["requestId"] != headers2["requestId"]


class TestSignRequest:
    """Tests for sign_request (backward-compatible wrapper)."""

    def test_sign_request_returns_bearer_headers(self, auth_instance):
        """Test that sign_request returns Bearer auth headers."""
        headers = auth_instance.sign_request({"some": "params"})

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test_access_token"
        assert "requestId" in headers

    def test_sign_request_ignores_params(self, auth_instance):
        """Test that sign_request works regardless of params passed."""
        headers_with_params = auth_instance.sign_request({"key": "value"})
        headers_without_params = auth_instance.sign_request(None)

        # Both should have the same auth structure
        assert headers_with_params["Authorization"] == headers_without_params["Authorization"]


# Feature: navimow-home-assistant, Property 3: Token Refresh on Expiry

from hypothesis import given, settings, assume
from hypothesis import strategies as st


class TestTokenRefreshOnExpiryProperty:
    """Property-based tests for token refresh on expiry.

    **Validates: Requirements 1.3, 17.1**

    Property 3: Token Refresh on Expiry
    For any API request made when the current access token's expiry time is in
    the past (or within 60s of expiry), the auth layer SHALL attempt a token
    refresh before executing the request, and the request SHALL be sent with
    the new token (not the expired one).
    """

    @settings(max_examples=100)
    @given(
        seconds_in_past=st.integers(min_value=1, max_value=365 * 24 * 3600),
    )
    @pytest.mark.asyncio
    async def test_expired_token_triggers_refresh(self, seconds_in_past: int):
        """For any token expiry time in the past, calling async_get_access_token
        triggers a refresh and returns the NEW token."""
        # Generate an expiry time that is in the past
        expired_expiry = datetime.now(timezone.utc) - timedelta(seconds=seconds_in_past)

        # Set up mock session with a valid refresh response
        mock_session = AsyncMock()
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value={
            "access_token": "refreshed_new_token",
            "refresh_token": "refreshed_new_refresh",
            "expires_in": 7200,
        })
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=response)

        callback = AsyncMock()

        auth = NavimowAuth(
            session=mock_session,
            region="fra",
            access_token="old_expired_token",
            refresh_token="test_refresh_token",
            token_expiry=expired_expiry,
            on_token_refresh=callback,
        )

        # Call async_get_access_token - should trigger refresh
        token = await auth.async_get_access_token()

        # The returned token must be the NEW token, not the expired one
        assert token == "refreshed_new_token"
        assert token != "old_expired_token"

        # The refresh callback must have been called
        callback.assert_called_once()

        # The session.post must have been called (refresh request)
        mock_session.post.assert_called_once()

    @settings(max_examples=100)
    @given(
        seconds_in_future=st.integers(min_value=61, max_value=365 * 24 * 3600),
    )
    @pytest.mark.asyncio
    async def test_valid_token_does_not_trigger_refresh(self, seconds_in_future: int):
        """For any token expiry time more than 60s in the future, calling
        async_get_access_token returns the current token without refresh."""
        # Generate an expiry time that is well in the future (beyond 60s buffer)
        valid_expiry = datetime.now(timezone.utc) + timedelta(seconds=seconds_in_future)

        mock_session = AsyncMock()
        callback = AsyncMock()

        auth = NavimowAuth(
            session=mock_session,
            region="fra",
            access_token="current_valid_token",
            refresh_token="test_refresh_token",
            token_expiry=valid_expiry,
            on_token_refresh=callback,
        )

        # Call async_get_access_token - should NOT trigger refresh
        token = await auth.async_get_access_token()

        # The returned token must be the current (non-expired) token
        assert token == "current_valid_token"

        # The refresh callback must NOT have been called
        callback.assert_not_called()

        # No HTTP request should have been made
        mock_session.post.assert_not_called()

    @settings(max_examples=100)
    @given(
        seconds_in_past=st.integers(min_value=1, max_value=365 * 24 * 3600),
        new_token=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
            min_size=5,
            max_size=50,
        ),
    )
    @pytest.mark.asyncio
    async def test_refreshed_token_is_used_not_expired_one(
        self, seconds_in_past: int, new_token: str
    ):
        """After refresh, the returned token is the NEW token (not the expired one).
        This holds for any generated new token value."""
        assume(new_token != "old_expired_token")

        expired_expiry = datetime.now(timezone.utc) - timedelta(seconds=seconds_in_past)

        mock_session = AsyncMock()
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value={
            "access_token": new_token,
            "refresh_token": "new_refresh",
            "expires_in": 3600,
        })
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=response)

        callback = AsyncMock()

        auth = NavimowAuth(
            session=mock_session,
            region="fra",
            access_token="old_expired_token",
            refresh_token="test_refresh_token",
            token_expiry=expired_expiry,
            on_token_refresh=callback,
        )

        token = await auth.async_get_access_token()

        # The returned token MUST be the new token from the refresh response
        assert token == new_token
        # It must NOT be the old expired token
        assert token != "old_expired_token"
