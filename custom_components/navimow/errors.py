"""Error code mapping and custom exceptions for the Navimow integration."""

from __future__ import annotations


class NavimowApiError(Exception):
    """Raised when an API request fails."""

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        """Initialize the error.

        Args:
            message: Human-readable error description.
            retry_after: Seconds to wait before retrying (for rate limiting).
        """
        super().__init__(message)
        self.retry_after = retry_after


class NavimowAuthError(Exception):
    """Raised when authentication fails."""


class NavimowCommandError(Exception):
    """Raised when a mower command fails.

    This typically occurs when the mower is in an incompatible state
    for the requested command (e.g., trying to dock when already docked).
    """

    def __init__(self, message: str, *, error_code: int | None = None) -> None:
        """Initialize the error.

        Args:
            message: Human-readable error description.
            error_code: Optional error code from the API response.
        """
        super().__init__(message)
        self.error_code = error_code


# Vehicle error codes (1-69): common robotic mower issues
VEHICLE_ERROR_CODES: dict[int, str] = {
    0: "No error",
    1: "Mower lifted",
    2: "Mower stuck",
    3: "Blade motor blocked",
    4: "Blade motor overload",
    5: "Left wheel motor blocked",
    6: "Right wheel motor blocked",
    7: "Left wheel motor overload",
    8: "Right wheel motor overload",
    9: "Left wheel motor stall",
    10: "Right wheel motor stall",
    11: "Boundary wire signal lost",
    12: "Boundary wire broken",
    13: "Charging station not found",
    14: "Charging contact error",
    15: "Charging voltage abnormal",
    16: "Charging current abnormal",
    17: "Battery temperature too high",
    18: "Battery temperature too low",
    19: "Battery voltage abnormal",
    20: "Battery charging timeout",
    21: "Battery cell imbalance",
    22: "GPS signal lost",
    23: "GPS antenna error",
    24: "RTK signal weak",
    25: "RTK fix lost",
    26: "RTK communication error",
    27: "IMU sensor error",
    28: "IMU calibration needed",
    29: "Tilt sensor triggered",
    30: "Collision sensor error",
    31: "Ultrasonic sensor error",
    32: "Rain sensor triggered",
    33: "Lift sensor error",
    34: "Bumper sensor stuck",
    35: "Front bumper triggered",
    36: "Motor driver error",
    37: "Main board communication error",
    38: "Blade motor driver error",
    39: "Left wheel driver error",
    40: "Right wheel driver error",
    41: "Communication timeout",
    42: "Internal communication error",
    43: "Firmware mismatch",
    44: "System overheated",
    45: "Fan motor error",
    46: "Power supply error",
    47: "Emergency stop activated",
    48: "Anti-theft alarm triggered",
    49: "Mower flipped over",
    50: "Slope too steep",
    51: "Wheel slip detected",
    52: "Mowing area too narrow",
    53: "Obstacle detected",
    54: "Vision sensor error",
    55: "Vision sensor blocked",
    56: "VisionFence boundary crossed",
    57: "Cellular module error",
    58: "Wi-Fi module error",
    59: "Bluetooth module error",
    60: "IoT module communication error",
    61: "OTA update failed",
    62: "Insufficient battery for task",
    63: "Task cancelled by user",
    64: "Schedule conflict",
    65: "Docking alignment failed",
    66: "Charging station communication error",
    67: "Map data not available",
    68: "Zone boundary error",
    69: "Mower outside boundary",
}

# Map error codes (1-9): map-related issues
MAP_ERROR_CODES: dict[int, str] = {
    0: "No error",
    1: "Map data corrupted",
    2: "Boundary incomplete",
    3: "Zone overlap detected",
    4: "Map area too large",
    5: "Map area too small",
    6: "Island boundary invalid",
    7: "Channel path invalid",
    8: "Map version mismatch",
    9: "Map upload failed",
}


def get_error_message(code: int, error_type: str = "vehicle") -> str:
    """Look up the human-readable message for an error code.

    Args:
        code: The error code integer.
        error_type: Type of error - "vehicle" or "map".

    Returns:
        Human-readable error message string.
        Returns empty string for code 0.
        Returns "Unknown error (code: X)" for unrecognized codes.
    """
    if code == 0:
        return ""

    if error_type == "map":
        message = MAP_ERROR_CODES.get(code)
    else:
        message = VEHICLE_ERROR_CODES.get(code)

    if message is None:
        return f"Unknown {error_type} error (code: {code})"

    return message
