"""Property-based tests for data model state mappings."""

import importlib.util
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Load the models module directly to avoid homeassistant dependency
_spec = importlib.util.spec_from_file_location(
    "models", "custom_components/navimow/models.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["models"] = _mod
_spec.loader.exec_module(_mod)

MowerState = _mod.MowerState
LawnMowerActivity = _mod.LawnMowerActivity
API_STATE_CODES = _mod.API_STATE_CODES
MOWER_STATE_TO_ACTIVITY = _mod.MOWER_STATE_TO_ACTIVITY
map_api_state_to_mower_state = _mod.map_api_state_to_mower_state
map_mower_state_to_activity = _mod.map_mower_state_to_activity


# Feature: navimow-home-assistant, Property 6: API State Code to MowerState Mapping
class TestAPIStateCodeToMowerStateMapping:
    """Property-based tests for API state code to MowerState mapping.

    **Validates: Requirements 5.1, 9.1**
    """

    @given(state_code=st.sampled_from(list(API_STATE_CODES.keys())))
    @settings(max_examples=100)
    def test_every_valid_api_state_code_maps_to_exactly_one_mower_state(
        self, state_code: str
    ) -> None:
        """For every valid API state code, map_api_state_to_mower_state returns
        exactly one MowerState value.

        **Validates: Requirements 5.1**
        """
        result = map_api_state_to_mower_state(state_code)

        # Result is exactly one MowerState enum member
        assert isinstance(result, MowerState)
        assert result in MowerState

    @given(state_code=st.sampled_from(list(API_STATE_CODES.keys())))
    @settings(max_examples=100)
    def test_result_is_always_a_valid_mower_state_enum_member(
        self, state_code: str
    ) -> None:
        """The result is always a valid MowerState enum member.

        **Validates: Requirements 5.1**
        """
        result = map_api_state_to_mower_state(state_code)

        # Verify it's a member of the MowerState enum
        assert result.value in [s.value for s in MowerState]

    @given(
        suffix=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=100)
    def test_any_error_prefix_string_maps_to_mower_state_error(
        self, suffix: str
    ) -> None:
        """Any string starting with 'ERROR_' maps to MowerState.ERROR.

        **Validates: Requirements 5.1**
        """
        error_code = f"ERROR_{suffix}"
        result = map_api_state_to_mower_state(error_code)

        assert result == MowerState.ERROR


# Feature: navimow-home-assistant, Property 7: MowerState to LawnMowerActivity Mapping
class TestMowerStateToLawnMowerActivityMapping:
    """Property-based tests for MowerState to LawnMowerActivity mapping.

    **Validates: Requirements 5.1, 9.1**
    """

    @given(state=st.sampled_from(MowerState))
    @settings(max_examples=100)
    def test_every_mower_state_maps_to_exactly_one_lawn_mower_activity(
        self, state: MowerState
    ) -> None:
        """For every MowerState value, map_mower_state_to_activity returns
        exactly one LawnMowerActivity.

        **Validates: Requirements 9.1**
        """
        result = map_mower_state_to_activity(state)

        # Result is exactly one LawnMowerActivity enum member
        assert isinstance(result, LawnMowerActivity)
        assert result in LawnMowerActivity

    def test_mapping_is_total_covers_all_mower_state_variants(self) -> None:
        """The mapping is total (covers all MowerState variants).

        **Validates: Requirements 9.1**
        """
        for state in MowerState:
            result = map_mower_state_to_activity(state)
            assert isinstance(result, LawnMowerActivity)

    @given(state=st.sampled_from(MowerState))
    @settings(max_examples=100)
    def test_result_is_always_a_valid_lawn_mower_activity_enum_member(
        self, state: MowerState
    ) -> None:
        """The result is always a valid LawnMowerActivity enum member.

        **Validates: Requirements 9.1**
        """
        result = map_mower_state_to_activity(state)

        valid_activities = {
            LawnMowerActivity.MOWING,
            LawnMowerActivity.DOCKED,
            LawnMowerActivity.PAUSED,
            LawnMowerActivity.RETURNING,
            LawnMowerActivity.ERROR,
        }
        assert result in valid_activities
