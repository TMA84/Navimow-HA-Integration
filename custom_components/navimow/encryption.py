"""Ninebot API request signing for the Navimow integration."""

import hashlib
import hmac
import secrets


class NbEncryption:
    """Ninebot API request signing."""

    APP_FROM = "navimow"
    APP_BRAND = "Android"

    @staticmethod
    def sign_params(
        params: dict[str, str],
        access_token: str,
        timestamp: int,
        nonce: str,
    ) -> str:
        """Generate HMAC signature for API request parameters.

        The signing process:
        1. Sort parameters alphabetically by key
        2. Concatenate as key=value pairs joined by &
        3. Append timestamp and nonce to form the string to sign
        4. Compute HMAC-SHA256 using the access_token as the key

        Args:
            params: Dictionary of request parameters to sign.
            access_token: The current access token used as the HMAC key.
            timestamp: Unix timestamp for the request.
            nonce: Random nonce string for replay protection.

        Returns:
            Hex-encoded HMAC-SHA256 signature string.
        """
        # Sort parameters alphabetically and join as key=value&key=value
        sorted_params = "&".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )

        # Build the string to sign: sorted params + timestamp + nonce
        string_to_sign = f"{sorted_params}{timestamp}{nonce}"

        # Compute HMAC-SHA256 with access_token as the key
        signature = hmac.new(
            key=access_token.encode("utf-8"),
            msg=string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return signature

    @staticmethod
    def generate_nonce() -> str:
        """Generate random nonce for request signing.

        Returns:
            A random 32-character hex string.
        """
        return secrets.token_hex(16)

    @staticmethod
    def build_signed_headers(
        access_token: str,
        signature: str,
        timestamp: int,
        nonce: str,
    ) -> dict[str, str]:
        """Build HTTP headers with authentication and signature.

        Args:
            access_token: The current access token for Authorization header.
            signature: The HMAC signature from sign_params.
            timestamp: Unix timestamp used in signing.
            nonce: Nonce used in signing.

        Returns:
            Dictionary of HTTP headers for the signed request.
        """
        return {
            "Authorization": f"Bearer {access_token}",
            "appfrom": NbEncryption.APP_FROM,
            "appbrand": NbEncryption.APP_BRAND,
            "x-nonce": nonce,
            "x-timestamp": str(timestamp),
            "x-signature": signature,
        }
