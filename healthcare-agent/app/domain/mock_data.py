from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re


@dataclass(frozen=True)
class Patient:
    patient_id: str
    full_name: str
    phone_number: str
    date_of_birth: str


@dataclass
class Appointment:
    appointment_id: str
    patient_id: str
    clinician: str
    specialty: str
    datetime: str
    location: str
    status: str = "scheduled"
    alternate_slots: list[str] = field(default_factory=list)


PATIENTS: list[Patient] = [
    Patient( # Maria Silva, +1 (415) 555-1212, 20 march 1989
        patient_id="P001",
        full_name="Maria Silva",
        phone_number="+1 (415) 555-1212",
        date_of_birth="1989-03-20",
    ),
    Patient( # John Carter, (650) 555-0199, 5 november 1978
        patient_id="P002",
        full_name="John Carter",
        phone_number="(650) 555-0199",
        date_of_birth="1978-11-05",
    ),
]


APPOINTMENTS: dict[str, Appointment] = {
    "APT-1001": Appointment(
        appointment_id="APT-1001",
        patient_id="P001",
        clinician="Dr. Emily Nguyen",
        specialty="Cardiology",
        datetime="2026-05-20 10:00",
        location="Clinic A - Room 204",
        alternate_slots=["2026-05-21 09:00", "2026-05-22 14:30"],
    ),
    "APT-1002": Appointment(
        appointment_id="APT-1002",
        patient_id="P001",
        clinician="Dr. Alan Brooks",
        specialty="Dermatology",
        datetime="2026-06-02 15:30",
        location="Clinic B - Room 12",
        alternate_slots=["2026-06-03 10:15", "2026-06-04 11:45"],
    ),
    "APT-1003": Appointment(
        appointment_id="APT-1003",
        patient_id="P001",
        clinician="Dr. Priya Patel",
        specialty="General Practice",
        datetime="2026-06-10 08:30",
        location="Clinic A - Room 101",
        alternate_slots=["2026-06-10 13:00", "2026-06-11 09:30"],
    ),
    "APT-2001": Appointment(
        appointment_id="APT-2001",
        patient_id="P002",
        clinician="Dr. Zoe Kim",
        specialty="Orthopedics",
        datetime="2026-05-25 11:00",
        location="Clinic C - Room 8",
        alternate_slots=["2026-05-26 09:00", "2026-05-27 16:00"],
    ),
}


def normalize_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value)


def _phones_match(a: str, b: str) -> bool:
    if a == b:
        return True

    # Accept common US format variants with or without leading country code "1".
    if len(a) == 10 and len(b) == 11 and b.startswith("1"):
        return a == b[1:]
    if len(b) == 10 and len(a) == 11 and a.startswith("1"):
        return b == a[1:]

    return False


def normalize_dob(value: str) -> str | None:
    candidate = value.strip()
    known_formats = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d")

    for fmt in known_formats:
        try:
            return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def find_patient(full_name: str, phone_number: str, date_of_birth: str) -> Patient | None:
    normalized_name = normalize_name(full_name)
    normalized_phone = normalize_phone(phone_number)
    normalized_dob = normalize_dob(date_of_birth)
    if normalized_dob is None:
        return None

    for patient in PATIENTS:
        if (
            normalize_name(patient.full_name) == normalized_name
            and _phones_match(normalize_phone(patient.phone_number), normalized_phone)
            and patient.date_of_birth == normalized_dob
        ):
            return patient

    return None


def get_appointments_for_patient(patient_id: str) -> list[Appointment]:
    items = [appt for appt in APPOINTMENTS.values() if appt.patient_id == patient_id]
    return sorted(items, key=lambda appt: appt.datetime)


def reset_appointments() -> None:
    APPOINTMENTS["APT-1001"].status = "scheduled"
    APPOINTMENTS["APT-1001"].datetime = "2026-05-20 10:00"

    APPOINTMENTS["APT-1002"].status = "scheduled"
    APPOINTMENTS["APT-1002"].datetime = "2026-06-02 15:30"

    APPOINTMENTS["APT-1003"].status = "scheduled"
    APPOINTMENTS["APT-1003"].datetime = "2026-06-10 08:30"

    APPOINTMENTS["APT-2001"].status = "scheduled"
    APPOINTMENTS["APT-2001"].datetime = "2026-05-25 11:00"
