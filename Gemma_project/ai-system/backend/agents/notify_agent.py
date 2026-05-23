from backend.database.db import log_notification

AGENT_NAME = "notify_agent"


def _build_message(booking: dict, patient: dict) -> str:
    return (
        f"Dear {patient.get('name', 'Patient')},\n\n"
        f"Your appointment has been confirmed!\n\n"
        f"  Doctor:    {booking.get('doctor_name', 'N/A')}\n"
        f"  Specialty: {booking.get('specialty', 'N/A').title()}\n"
        f"  Date:      {booking.get('date', 'N/A')}\n"
        f"  Time:      {booking.get('time', 'N/A')}\n"
        f"  Ref #:     {booking.get('appointment_id', 'N/A')}\n\n"
        f"Please arrive 15 minutes early. Call 555-HOSPITAL to reschedule.\n\n"
        f"Medical AI System"
    )


def run(state: dict) -> dict:
    print(f"[{AGENT_NAME}] Sending notifications...")
    booking = state.get("booking", {})
    patient = state.get("patient", {})
    workflow_id = state.get("workflow_id", "WF-000")
    patient_id = patient.get("id")

    if not booking:
        state["step_results"] = state.get("step_results", {})
        state["step_results"]["send_confirmation"] = {
            "status": "skipped",
            "reason": "no_booking_to_notify",
        }
        return state

    message = _build_message(booking, patient)

    # Simulate SMS
    phone = patient.get("phone", "")
    if phone:
        print(f"\n[{AGENT_NAME}] === SMS to {phone} ===")
        print(message)
        if patient_id:
            try:
                log_notification(patient_id, workflow_id, "sms", phone, message)
            except Exception:
                pass

    # Simulate email
    email = patient.get("email", "")
    if email:
        print(f"\n[{AGENT_NAME}] === EMAIL to {email} ===")
        print(message)
        if patient_id:
            try:
                log_notification(patient_id, workflow_id, "email", email, message)
            except Exception:
                pass

    if not phone and not email:
        print(f"\n[{AGENT_NAME}] === CONSOLE notification ===")
        print(message)

    state["notification_sent"] = True
    state["step_results"] = state.get("step_results", {})
    state["step_results"]["send_confirmation"] = {
        "status": "sent",
        "channels": [c for c in ["sms", "email"] if patient.get({"sms": "phone", "email": "email"}[c])],
        "preview": message[:100],
    }
    print(f"[{AGENT_NAME}] Notifications sent successfully")
    return state
