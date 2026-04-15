from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import tool

from app.domain.mock_data import APPOINTMENTS, find_patient, get_appointments_for_patient, normalize_dob
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


def _session_or_message() -> tuple[SessionState | None, str | None]:
    session = get_current_session()
    if session is None:
        return None, "Internal error: no active thread context was provided."
    return session, None


def _require_verified_session() -> tuple[SessionState | None, str | None]:
    session, err = _session_or_message()
    if err:
        return None, err
    if not session.verified_patient_id:
        return (
            None,
            "Before I can access appointments, I need to verify your identity. "
            "Please share your full name, phone number, and date of birth (YYYY-MM-DD).",
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
) -> str:
    """Verify patient identity before any appointment actions.

    Args:
        full_name: Patient full legal name
        phone_number: Patient phone number
        date_of_birth: Date of birth, preferably YYYY-MM-DD
    """
    session, err = _session_or_message()
    if err:
        return err

    if full_name.strip():
        session.identity_fields["full_name"] = full_name.strip()
    if phone_number.strip():
        session.identity_fields["phone_number"] = phone_number.strip()
    if date_of_birth.strip():
        normalized = normalize_dob(date_of_birth)
        if normalized is None:
            return (
                "I couldn't parse the date of birth. Please use YYYY-MM-DD "
                "(for example, 1989-03-20)."
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
        return f"Thanks. I still need your {missing_label} to verify your identity."

    patient = find_patient(
        session.identity_fields["full_name"],
        session.identity_fields["phone_number"],
        session.identity_fields["date_of_birth"],
    )
    if patient is None:
        return (
            "I couldn't match those details to a patient record. "
            "Please check your full name, phone number, and date of birth and try again."
        )

    session.verified_patient_id = patient.patient_id
    return (
        f"Verification successful for {patient.full_name}. "
        "You can now list, confirm, cancel, or reschedule appointments."
    )


@tool
def list_appointments() -> str:
    """List appointments for the verified patient."""
    session, err = _require_verified_session()
    if err:
        return err

    appointments = get_appointments_for_patient(session.verified_patient_id)
    session.last_listed_appointment_ids = [item.appointment_id for item in appointments]

    if not appointments:
        return "You currently have no appointments on file."

    lines = [_format_appointment_line(index, appt) for index, appt in enumerate(appointments, start=1)]
    return "Here are your appointments:\n" + "\n".join(lines)


@tool
def confirm_appointment(appointment_reference: str) -> str:
    """Confirm one appointment by ID (e.g. APT-1001) or ordinal (e.g. second one).

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
        return "I couldn't identify that appointment. Please provide an appointment ID or list appointments first."

    appointment = APPOINTMENTS.get(appointment_id)
    if appointment is None or appointment.patient_id != session.verified_patient_id:
        return "That appointment was not found for your account."

    if appointment.status == "canceled":
        return "This appointment is already canceled and cannot be confirmed."
    if appointment.status == "confirmed":
        return "This appointment is already confirmed."

    appointment.status = "confirmed"
    return f"Appointment {appointment.appointment_id} is now confirmed."


@tool
def cancel_appointment(appointment_reference: str) -> str:
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
        return "I couldn't identify that appointment. Please provide an appointment ID or list appointments first."

    appointment = APPOINTMENTS.get(appointment_id)
    if appointment is None or appointment.patient_id != session.verified_patient_id:
        return "That appointment was not found for your account."

    if appointment.status == "canceled":
        return "This appointment is already canceled."

    appointment.status = "canceled"
    return f"Appointment {appointment.appointment_id} has been canceled."


@tool
def reschedule_appointment(appointment_reference: str, new_time_slot: str = "") -> str:
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
        return "I couldn't identify that appointment. Please provide an appointment ID or list appointments first."

    appointment = APPOINTMENTS.get(appointment_id)
    if appointment is None or appointment.patient_id != session.verified_patient_id:
        return "That appointment was not found for your account."

    if appointment.status == "canceled":
        return "This appointment is canceled and cannot be rescheduled."

    if not new_time_slot.strip():
        options = "\n".join(f"- {slot}" for slot in appointment.alternate_slots)
        return (
            f"Available alternate slots for {appointment.appointment_id}:\n{options}\n"
            "Tell me which slot you prefer, and I can apply it."
        )

    selected_slot = new_time_slot.strip()
    if selected_slot not in appointment.alternate_slots:
        options = ", ".join(appointment.alternate_slots)
        return f"That slot is not available. Please choose one of: {options}."

    appointment.datetime = selected_slot
    appointment.status = "rescheduled"
    return f"Appointment {appointment.appointment_id} has been rescheduled to {selected_slot}."


ALL_TOOLS = [
    verify_patient,
    list_appointments,
    confirm_appointment,
    cancel_appointment,
    reschedule_appointment,
]
