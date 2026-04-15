from session_store import bind_thread, get_session, reset_all_sessions
from mock_data import APPOINTMENTS, reset_appointments
from tools import (
    cancel_appointment,
    confirm_appointment,
    list_appointments,
    reschedule_appointment,
    verify_patient,
)


def _invoke(tool_obj, /, **kwargs):
    return tool_obj.invoke(kwargs)


def setup_function():
    reset_all_sessions()
    reset_appointments()


def test_pre_verification_refusal_then_progressive_verification_then_actions():
    thread_id = "thread-1"

    with bind_thread(thread_id):
        refusal = _invoke(list_appointments)
        assert "verify your identity" in refusal.lower()

        step1 = _invoke(verify_patient, full_name="Maria Silva")
        assert "still need your phone number, date of birth" in step1

        step2 = _invoke(verify_patient, phone_number="+1 415 555 1212", date_of_birth="1989-03-20")
        assert "Verification successful" in step2

        listing = _invoke(list_appointments)
        assert "APT-1001" in listing
        assert "APT-1002" in listing
        assert "APT-1003" in listing

        confirm_result = _invoke(confirm_appointment, appointment_reference="the first one")
        assert "is now confirmed" in confirm_result
        assert APPOINTMENTS["APT-1001"].status == "confirmed"

        relist = _invoke(list_appointments)
        assert "status: confirmed" in relist

        options = _invoke(reschedule_appointment, appointment_reference="APT-1002")
        assert "Available alternate slots" in options

        chosen = _invoke(
            reschedule_appointment,
            appointment_reference="APT-1002",
            new_time_slot="2026-06-03 10:15",
        )
        assert "has been rescheduled" in chosen
        assert APPOINTMENTS["APT-1002"].status == "rescheduled"
        assert APPOINTMENTS["APT-1002"].datetime == "2026-06-03 10:15"

        cancel_result = _invoke(cancel_appointment, appointment_reference="third")
        assert "has been canceled" in cancel_result
        assert APPOINTMENTS["APT-1003"].status == "canceled"

        repeat_cancel = _invoke(cancel_appointment, appointment_reference="APT-1003")
        assert "already canceled" in repeat_cancel


def test_new_thread_starts_unverified_even_if_another_thread_is_verified():
    with bind_thread("thread-a"):
        _invoke(verify_patient, full_name="Maria Silva", phone_number="4155551212", date_of_birth="1989-03-20")
        assert get_session("thread-a").verified_patient_id == "P001"

    with bind_thread("thread-b"):
        response = _invoke(confirm_appointment, appointment_reference="APT-1001")
        assert "verify your identity" in response.lower()
        assert get_session("thread-b").verified_patient_id is None
