"""Tests for life_activity module.

TC-LIFE-01 .. TC-LIFE-05
FR-LIFE-01: Daily life activity catalogue.
"""

from __future__ import annotations

from orchestrator.life_activity import (
    _ACTIVITY_CATALOGUE,
    ActivityType,
    LifeActivity,
    get_activity,
)


# TC-LIFE-01: get_activity returns LifeActivity with correct activity_type
def test_get_activity_returns_correct_type():
    for act_type in ActivityType:
        activity = get_activity(act_type)
        assert isinstance(activity, LifeActivity)
        assert activity.activity_type == act_type


# TC-LIFE-02: all ActivityType values have catalogue entries
def test_all_activity_types_have_catalogue_entries():
    for act_type in ActivityType:
        assert act_type in _ACTIVITY_CATALOGUE, f"{act_type} missing from catalogue"
        assert len(_ACTIVITY_CATALOGUE[act_type]) >= 1


# TC-LIFE-03: SLEEP activity is_sleeping returns True
def test_sleep_activity_is_sleeping_true():
    activity = get_activity(ActivityType.SLEEP)
    assert activity.is_sleeping is True


# TC-LIFE-04: non-SLEEP activities is_sleeping returns False
def test_non_sleep_activities_is_sleeping_false():
    for act_type in ActivityType:
        if act_type == ActivityType.SLEEP:
            continue
        activity = get_activity(act_type)
        assert activity.is_sleeping is False, f"{act_type}.is_sleeping should be False"


# TC-LIFE-05a: READ catalogue has multiple entries (variety)
def test_read_has_multiple_catalogue_entries():
    assert len(_ACTIVITY_CATALOGUE[ActivityType.READ]) >= 2


# TC-LIFE-05b: get_activity(READ) returns variety across multiple calls
def test_get_activity_returns_variety_for_read():
    hints = {get_activity(ActivityType.READ).idle_hint for _ in range(30)}
    # At least 2 distinct hints from 3 catalogue entries
    assert len(hints) >= 2


# TC-LIFE-05c: all LifeActivities have non-empty gesture
def test_all_activities_have_non_empty_gesture():
    for act_type, activities in _ACTIVITY_CATALOGUE.items():
        for a in activities:
            assert a.gesture, f"{act_type} has empty gesture"


# TC-LIFE-05d: all LifeActivities have positive duration_sec
def test_all_activities_have_positive_duration():
    for act_type, activities in _ACTIVITY_CATALOGUE.items():
        for a in activities:
            assert a.duration_sec > 0, f"{act_type} has non-positive duration_sec"
