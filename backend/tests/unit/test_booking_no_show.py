"""BookingStatus.NO_SHOW: state-machine edges are pure, no DB needed."""

from app.domain.booking.models import BOOKING_STATUS_TRANSITIONS, BookingStatus


def test_no_show_is_a_real_enum_value():
    assert BookingStatus.NO_SHOW == "no_show"


def test_no_show_reachable_from_pre_in_progress_states():
    reachable_from = {
        BookingStatus.CONFIRMED,
        BookingStatus.ASSIGNED,
        BookingStatus.ON_MY_WAY,
        BookingStatus.ARRIVED,
        BookingStatus.DELAYED,
    }
    for status in reachable_from:
        assert BookingStatus.NO_SHOW in BOOKING_STATUS_TRANSITIONS[status]


def test_no_show_not_reachable_from_pending_or_in_progress():
    # PENDING: nobody has confirmed a time yet, so "didn't show up" doesn't apply.
    # IN_PROGRESS: the job is already underway, so a no-show is no longer possible.
    assert BookingStatus.NO_SHOW not in BOOKING_STATUS_TRANSITIONS[BookingStatus.PENDING]
    assert BookingStatus.NO_SHOW not in BOOKING_STATUS_TRANSITIONS[BookingStatus.IN_PROGRESS]


def test_no_show_is_terminal():
    assert BOOKING_STATUS_TRANSITIONS[BookingStatus.NO_SHOW] == set()
