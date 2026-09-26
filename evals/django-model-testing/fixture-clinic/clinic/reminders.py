"""Outgoing messages to patients. The mail gateway is only reachable from production."""


def send_booking_confirmation(appointment_id: int) -> None:
    """Email the patient that the appointment is booked."""
