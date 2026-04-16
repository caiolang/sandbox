from app.domain.mock_data import APPOINTMENTS, reset_appointments
from app.session.store import bind_thread, get_session, reset_all_sessions
from app.tools.appointment_tools import (
    cancel_appointment,
    confirm_appointment,
    list_appointments,
    reschedule_appointment,
    verify_patient,
)


def _invoke(tool_obj, /, **kwargs):
    """Invoke a LangChain tool using the same dict input shape as agent calls."""
    return tool_obj.invoke(kwargs)


def setup_function():
    reset_all_sessions()
    reset_appointments()


def test_pre_verification_refusal_then_progressive_verification_then_actions():
    thread_id = "thread-1"

    with bind_thread(thread_id):
        refusal = _invoke(list_appointments)
        assert refusal["ok"] is False
        assert refusal["error_code"] == "not_verified"

        step1 = _invoke(verify_patient, full_name="Maria Silva")
        assert step1["ok"] is False
        assert step1["error_code"] == "missing_identity_fields"
        assert step1["missing_fields"] == ["phone_number", "date_of_birth"]

        step2 = _invoke(verify_patient, phone_number="+1 415 555 1212", date_of_birth="1989-03-20")
        assert step2["ok"] is True
        assert step2["patient_id"] == "P001"

        listing = _invoke(list_appointments)
        assert listing["ok"] is True
        ids = [item["appointment_id"] for item in listing["appointments"]]
        assert ids == ["APT-1001", "APT-1002", "APT-1003"]

        confirm_result = _invoke(confirm_appointment, appointment_reference="the first one")
        assert confirm_result["ok"] is True
        assert confirm_result["appointment_id"] == "APT-1001"
        assert APPOINTMENTS["APT-1001"].status == "confirmed"

        relist = _invoke(list_appointments)
        assert relist["ok"] is True
        assert relist["appointments"][0]["status"] == "confirmed"

        options = _invoke(reschedule_appointment, appointment_reference="APT-1002")
        assert options["ok"] is True
        assert options["appointment_id"] == "APT-1002"
        assert options["alternate_slots"] == ["2026-06-03 10:15", "2026-06-04 11:45"]

        chosen = _invoke(
            reschedule_appointment,
            appointment_reference="APT-1002",
            new_time_slot="2026-06-03 10:15",
        )
        assert chosen["ok"] is True
        assert chosen["new_time_slot"] == "2026-06-03 10:15"
        assert APPOINTMENTS["APT-1002"].status == "rescheduled"
        assert APPOINTMENTS["APT-1002"].datetime == "2026-06-03 10:15"

        cancel_result = _invoke(cancel_appointment, appointment_reference="third")
        assert cancel_result["ok"] is True
        assert cancel_result["appointment_id"] == "APT-1003"
        assert APPOINTMENTS["APT-1003"].status == "canceled"

        repeat_cancel = _invoke(cancel_appointment, appointment_reference="APT-1003")
        assert repeat_cancel["ok"] is True
        assert repeat_cancel["appointment_id"] == "APT-1003"


def test_new_thread_starts_unverified_even_if_another_thread_is_verified():
    with bind_thread("thread-a"):
        verify = _invoke(verify_patient, full_name="Maria Silva", phone_number="4155551212", date_of_birth="1989-03-20")
        assert verify["ok"] is True
        assert get_session("thread-a").verified_patient_id == "P001"

    with bind_thread("thread-b"):
        response = _invoke(confirm_appointment, appointment_reference="APT-1001")
        assert response["ok"] is False
        assert response["error_code"] == "not_verified"
        assert get_session("thread-b").verified_patient_id is None


def test_verify_patient_rejects_unparseable_dob():
    with bind_thread("bad-dob"):
        response = _invoke(
            verify_patient,
            full_name="Maria Silva",
            phone_number="+1 415 555 1212",
            date_of_birth="20-03-1989",
        )
        assert response["ok"] is False
        assert response["error_code"] == "invalid_dob_format"
        assert "date_of_birth" not in get_session("bad-dob").identity_fields


def test_unknown_patient_does_not_get_verified():
    with bind_thread("unknown-patient"):
        response = _invoke(
            verify_patient,
            full_name="Maria Silva",
            phone_number="4155550000",
            date_of_birth="1989-03-20",
        )
        assert response["ok"] is False
        assert response["error_code"] == "patient_not_found"
        assert get_session("unknown-patient").verified_patient_id is None


def test_confirm_by_id_works_without_listing_first():
    with bind_thread("confirm-by-id"):
        verify = _invoke(
            verify_patient,
            full_name="Maria Silva",
            phone_number="4155551212",
            date_of_birth="1989-03-20",
        )
        assert verify["ok"] is True

        response = _invoke(confirm_appointment, appointment_reference="apt-1001")
        assert response["ok"] is True
        assert response["appointment_id"] == "APT-1001"
        assert APPOINTMENTS["APT-1001"].status == "confirmed"


def test_reschedule_invalid_slot_does_not_change_appointment():
    with bind_thread("invalid-slot"):
        verify = _invoke(
            verify_patient,
            full_name="Maria Silva",
            phone_number="4155551212",
            date_of_birth="1989-03-20",
        )
        assert verify["ok"] is True

        original_datetime = APPOINTMENTS["APT-1002"].datetime
        response = _invoke(
            reschedule_appointment,
            appointment_reference="APT-1002",
            new_time_slot="2026-07-01 09:00",
        )
        assert response["ok"] is False
        assert response["error_code"] == "slot_not_available"
        assert response["alternate_slots"] == ["2026-06-03 10:15", "2026-06-04 11:45"]
        assert APPOINTMENTS["APT-1002"].status == "scheduled"
        assert APPOINTMENTS["APT-1002"].datetime == original_datetime


def test_canceled_appointment_cannot_be_confirmed_again():
    with bind_thread("terminal-canceled"):
        verify = _invoke(
            verify_patient,
            full_name="Maria Silva",
            phone_number="4155551212",
            date_of_birth="1989-03-20",
        )
        assert verify["ok"] is True

        canceled = _invoke(cancel_appointment, appointment_reference="APT-1003")
        assert canceled["ok"] is True

        response = _invoke(confirm_appointment, appointment_reference="APT-1003")
        assert response["ok"] is False
        assert response["error_code"] == "invalid_status_transition"
