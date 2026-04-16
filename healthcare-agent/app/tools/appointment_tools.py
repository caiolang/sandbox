from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import tool

from app.domain.mock_data import (
    APPOINTMENTS,
    find_patient,
    get_appointments_for_patient,
    normalize_dob,
)
from app.session.store import SessionState, get_current_session


ORDINAL_MAP = {
    "first": 1,
    "1st": 1,
    "one": 1,
    "second": 2,
    "2nd": 2,
    "two": 2,
    "third": 3,
    "3rd": 3,
    "three": 3,
    "fourth": 4,
    "4th": 4,
    "four": 4,
    "fifth": 5,
    "5th": 5,
    "five": 5,
}


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "message": message}
    payload.update(extra)
    return payload


def _fail(message: str, error_code: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "message": message, "error_code": error_code}
    payload.update(extra)
    return payload


def _session_or_error() -> tuple[SessionState | None, dict[str, Any] | None]:
    session = get_current_session()
    if session is None:
        return None, _fail(
            "Internal error: no active thread context was provided.",
            "missing_thread_context",
        )
    return session, None


def _require_verified_session() -> tuple[SessionState | None, dict[str, Any] | None]:
    session, err = _session_or_error()
    if err:
        return None, err
    if not session.verified_patient_id:
        return (
            None,
            _fail(
                "Before I can access appointments, I need to verify your identity. "
                "Please share your full name, phone number, and date of birth (YYYY-MM-DD).",
                "not_verified",
            ),
        )
    return session, None


def _format_appointment_line(index: int, appointment: Any) -> str:
    return (
        f"{index}. ID: {appointment.appointment_id} | {appointment.specialty} with {appointment.clinician} | "
        f"{appointment.datetime} | {appointment.location} | status: {appointment.status}"
    )


def _resolve_appointment_id(reference: str, listed_ids: list[str]) -> str | None:
    candidate = reference.strip()
    if not candidate:
        return None

    uppercase = candidate.upper()
    if uppercase in APPOINTMENTS:
        return uppercase

    lowered = candidate.casefold()
    for token, ordinal in ORDINAL_MAP.items():
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            if 0 <= ordinal - 1 < len(listed_ids):
                return listed_ids[ordinal - 1]

    digit_match = re.search(r"\b(\d+)\b", lowered)
    if digit_match:
        ordinal = int(digit_match.group(1))
        if 0 <= ordinal - 1 < len(listed_ids):
            return listed_ids[ordinal - 1]

    return None


@tool
def verify_patient(
    full_name: str = "",
    phone_number: str = "",
    date_of_birth: str = "",
) -> dict[str, Any]:
    """Verify patient identity before any appointment actions.

    Args:
        full_name: Patient full legal name
        phone_number: Patient phone number
        date_of_birth: Date of birth, preferably YYYY-MM-DD
    """
    session, err = _session_or_error()
    if err:
        return err

    if full_name.strip():
        session.identity_fields["full_name"] = full_name.strip()
    if phone_number.strip():
        session.identity_fields["phone_number"] = phone_number.strip()
    if date_of_birth.strip():
        normalized = normalize_dob(date_of_birth)
        if normalized is None:
            return _fail(
                "I couldn't parse the date of birth. Please use YYYY-MM-DD "
                "(for example, 1989-03-20).",
                "invalid_dob_format",
            )
        session.identity_fields["date_of_birth"] = normalized

    missing = [
        key
        for key in ("full_name", "phone_number", "date_of_birth")
        if not session.identity_fields.get(key)
    ]
    if missing:
        labels = {
            "full_name": "full name",
            "phone_number": "phone number",
            "date_of_birth": "date of birth",
        }
        missing_label = ", ".join(labels[item] for item in missing)
        return _fail(
            f"STILL MISSING {missing_label}. ASK THE USER FOR THIS INFORMATION.",
            "missing_identity_fields",
            missing_fields=missing,
        )

    patient = find_patient(
        session.identity_fields["full_name"],
        session.identity_fields["phone_number"],
        session.identity_fields["date_of_birth"],
    )
    if patient is None:
        return _fail(
            "I couldn't match those details to a patient record. "
            "Please check your full name, phone number, and date of birth and try again.",
            "patient_not_found",
        )

    session.verified_patient_id = patient.patient_id
    return _ok(
        f"Verification successful for {patient.full_name}. "
        "You can now list, confirm, cancel, or reschedule appointments.",
        patient_id=patient.patient_id,
    )


@tool
def list_appointments() -> dict[str, Any]:
    """List appointments for the verified patient."""
    session, err = _require_verified_session()
    if err:
        return err

    appointments = get_appointments_for_patient(session.verified_patient_id)
    session.last_listed_appointment_ids = [item.appointment_id for item in appointments]

    if not appointments:
        return _ok("You currently have no appointments on file.", appointments=[])

    lines = [_format_appointment_line(index, appt) for index, appt in enumerate(appointments, start=1)]
    return _ok(
        "Here are your appointments:\n" + "\n".join(lines),
        appointments=[
            {
                "index": index,
                "appointment_id": appt.appointment_id,
                "clinician": appt.clinician,
                "specialty": appt.specialty,
                "datetime": appt.datetime,
                "location": appt.location,
                "status": appt.status,
            }
            for index, appt in enumerate(appointments, start=1)
        ],
    )


@tool
def confirm_appointment(appointment_reference: str) -> dict[str, Any]:
    """Based on the appointment the user wants to confirm, pass the respective ID (e.g. APT-1001) or ordinal (e.g. second one). No need to ask the user to use the ID, it will be used by YOU (the agent) to identify the appointment they want to confirm.

    Args:
        appointment_reference: Appointment ID or ordinal reference from the latest listed appointments
    """
    session, err = _require_verified_session()
    if err:
        return err

    appointment_id = _resolve_appointment_id(
        appointment_reference,
        session.last_listed_appointment_ids,
    )
    if not appointment_id:
        return _fail(
            "I couldn't identify that appointment. Please provide an appointment ID or list appointments first.",
            "appointment_not_identified",
        )

    appointment = APPOINTMENTS.get(appointment_id)
    if appointment is None or appointment.patient_id != session.verified_patient_id:
        return _fail("That appointment was not found for your account.", "appointment_not_found")

    if appointment.status == "canceled":
        return _fail(
            "This appointment is already canceled and cannot be confirmed.",
            "invalid_status_transition",
        )
    if appointment.status == "confirmed":
        return _ok("This appointment is already confirmed.", appointment_id=appointment.appointment_id)

    appointment.status = "confirmed"
    return _ok(
        f"Appointment {appointment.appointment_id} is now confirmed.",
        appointment_id=appointment.appointment_id,
    )


@tool
def cancel_appointment(appointment_reference: str) -> dict[str, Any]:
    """Cancel one appointment by ID (e.g. APT-1001) or ordinal (e.g. first one).

    Args:
        appointment_reference: Appointment ID or ordinal reference from the latest listed appointments
    """
    session, err = _require_verified_session()
    if err:
        return err

    appointment_id = _resolve_appointment_id(
        appointment_reference,
        session.last_listed_appointment_ids,
    )
    if not appointment_id:
        return _fail(
            "I couldn't identify that appointment. Please provide an appointment ID or list appointments first.",
            "appointment_not_identified",
        )

    appointment = APPOINTMENTS.get(appointment_id)
    if appointment is None or appointment.patient_id != session.verified_patient_id:
        return _fail("That appointment was not found for your account.", "appointment_not_found")

    if appointment.status == "canceled":
        return _ok("This appointment is already canceled.", appointment_id=appointment.appointment_id)

    appointment.status = "canceled"
    return _ok(
        f"Appointment {appointment.appointment_id} has been canceled.",
        appointment_id=appointment.appointment_id,
    )


@tool
def reschedule_appointment(appointment_reference: str, new_time_slot: str = "") -> dict[str, Any]:
    """Reschedule one appointment using predefined alternate slots.

    Args:
        appointment_reference: Appointment ID or ordinal reference from the latest listed appointments
        new_time_slot: One slot from the options returned by this tool
    """
    session, err = _require_verified_session()
    if err:
        return err

    appointment_id = _resolve_appointment_id(
        appointment_reference,
        session.last_listed_appointment_ids,
    )
    if not appointment_id:
        return _fail(
            "I couldn't identify that appointment. Please provide an appointment ID or list appointments first.",
            "appointment_not_identified",
        )

    appointment = APPOINTMENTS.get(appointment_id)
    if appointment is None or appointment.patient_id != session.verified_patient_id:
        return _fail("That appointment was not found for your account.", "appointment_not_found")

    if appointment.status == "canceled":
        return _fail(
            "This appointment is canceled and cannot be rescheduled.",
            "invalid_status_transition",
        )

    if not new_time_slot.strip():
        options = "\n".join(f"- {slot}" for slot in appointment.alternate_slots)
        return _ok(
            f"Available alternate slots for {appointment.appointment_id}:\n{options}\n"
            "Tell me which slot you prefer, and I can apply it.",
            appointment_id=appointment.appointment_id,
            alternate_slots=appointment.alternate_slots,
        )

    selected_slot = new_time_slot.strip()
    if selected_slot not in appointment.alternate_slots:
        options = ", ".join(appointment.alternate_slots)
        return _fail(
            f"That slot is not available. Please choose one of: {options}.",
            "slot_not_available",
            appointment_id=appointment.appointment_id,
            alternate_slots=appointment.alternate_slots,
        )

    appointment.datetime = selected_slot
    appointment.status = "rescheduled"
    return _ok(
        f"Appointment {appointment.appointment_id} has been rescheduled to {selected_slot}.",
        appointment_id=appointment.appointment_id,
        new_time_slot=selected_slot,
    )


ALL_TOOLS = [
    verify_patient,
    list_appointments,
    confirm_appointment,
    cancel_appointment,
    reschedule_appointment,
]
