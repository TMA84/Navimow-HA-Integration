"""Constants for the Navimow integration."""

from enum import IntEnum

DOMAIN = "navimow"

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "switch",
    "select",
    "number",
    "button",
    "lawn_mower",
    "device_tracker",
    "update",
]

# Polling intervals (seconds)
POLL_INTERVAL_ACTIVE = 10
POLL_INTERVAL_DEFAULT = 30
POLL_INTERVAL_IDLE = 60

# Supported regions
REGIONS = ["fra", "ore", "sg", "bj", "mos"]

# API URL templates
API_BASE_URL = "https://navimow-{region}.ninebot.com/"
PASSPORT_BASE_URL = "https://api-passport-{region}.ninebot.com/"


class IndexType(IntEnum):
    """Ninebot protocol IndexType constants for device data fields."""

    # GPS
    NINEIOT_GPS_LAT = 0x01
    NINEIOT_GPS_LNG = 0x02
    NINEIOT_GPS_ALTITUDE = 0x03
    NINEIOT_GPS_SPEED = 0x04
    NINEIOT_GPS_HDOP = 0x05
    NINEIOT_GPS_SAT_IN_USE = 0x06
    NINEIOT_GPS_SAT_IN_VIEW = 0x07
    NINEIOT_GPS_DATA_VALID = 0x08

    # Battery
    NINEIOT_BAT_LEVEL = 0x10
    NINEIOT_BAT_VOLT = 0x11
    NINEIOT_BAT_TEMP_FAULT = 0x12

    # Connectivity
    NINEIOT_DEVICE_TYPE = 0x20
    NINEIOT_GPRS_CSQ = 0x21
    NINEIOT_MQTT_STATE = 0x22
    NINEIOT_DEVICE_WIFI_SSID = 0x23

    # Mower state
    MOWER_STATE_BOOL = 0x30
    MOWER_QUERY = 0x31
    MOWER_SET = 0x32
    MOWER_HANDLE_MOW = 0x33
    MOWER_HANDLE_STOP = 0x34
    MOWER_HANDLE_PARK = 0x35
    MOWER_TEST_PROGRESS = 0x36

    # Task
    TASK_SET = 0x40
    TASK_STATE = 0x41

    # Map
    MAP_TOTAL_AREA = 0x50
