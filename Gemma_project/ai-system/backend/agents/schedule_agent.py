from datetime import datetime, timedelta
from backend.database.db import (
    get_available_slots_by_specialty,
    get_doctors_by_specialty,
    confirm_appointment,
)


DEMO_DOCTORS = {
    "cardiology":    "Dr. Sarah Chen",
    "neurology":     "Dr. James Wilson",
    "orthopedics":   "Dr. Maria Rodriguez",
    "dermatology":   "Dr. Lisa Park",
    "psychiatry":    "Dr. Alan Foster",
    "ophthalmology": "Dr. Nina Patel",
    "general":       "Dr. Emily Brown",
}


def _demo_slots(specialty: str) -> list:
    base = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    doctor = DEMO_DOCTORS.get(specialty.lower())
    if not doctor:
        # No specialist available — fall back to general and note it
        print(f"[{AGENT_NAME}] No demo doctor for specialty '{specialty}', falling back to general")
        specialty = "general"
        doctor = DEMO_DOCTORS["general"]
    return [
        {"id": 1001 + i, "datetime": (base + timedelta(days=i+1, hours=i*2)).isoformat(),
         "doctor_name": doctor, "specialty": specialty, "doctor_id": 99}
        for i in range(3)
    ]

AGENT_NAME = "schedule_agent"


def _format_slot(slot: dict) -> dict:
    dt: datetime = slot["datetime"]
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return {
        "slot_id":     slot["id"],
        "doctor_name": slot["doctor_name"],
        "specialty":   slot["specialty"],
        "doctor_id":   slot.get("doctor_id"),
        "date":        dt.strftime("%A, %B %d, %Y"),
        "time":        dt.strftime("%I:%M %p"),
        "datetime_iso": dt.isoformat(),
    }


def find_slots(state: dict) -> dict:
    print(f"[{AGENT_NAME}] Finding available slots...")
    specialty = state.get("specialty", "general")
    original_specialty = specialty
    try:
        raw_slots = get_available_slots_by_specialty(specialty, limit=3)
        if not raw_slots:
            print(f"[{AGENT_NAME}] No slots for '{specialty}', trying general")
            raw_slots = get_available_slots_by_specialty("general", limit=3)
            if raw_slots and specialty != "general":
                state["no_specialist_notice"] = f"No {specialty} specialist available. Showing general practitioners."
    except Exception as e:
        print(f"[{AGENT_NAME}] DB unavailable: {e}. Using demo slots.")
        raw_slots = _demo_slots(specialty)
        if state.get("no_specialist_notice") is None and specialty != raw_slots[0].get("specialty", specialty):
            state["no_specialist_notice"] = f"No {original_specialty} specialist available. Showing general practitioners."

    formatted = [_format_slot(s) for s in raw_slots]
    state["available_slots"] = formatted
    state["step_results"] = state.get("step_results", {})
    state["step_results"]["find_slots"] = {
        "status": "ok",
        "count": len(formatted),
        "slots": formatted,
    }
    print(f"[{AGENT_NAME}] Found {len(formatted)} slots for {specialty}")
    return state


def confirm(state: dict) -> dict:
    print(f"[{AGENT_NAME}] Confirming appointment...")
    selected_slot = state.get("selected_slot")
    patient = state.get("patient", {})
    patient_id = patient.get("id") or state.get("patient_id")
    workflow_id = state.get("workflow_id", "WF-000")
    symptoms = state.get("symptoms", [])
    reason = ", ".join(symptoms) if symptoms else "General appointment"

    if not selected_slot:
        state["errors"] = state.get("errors", []) + ["No slot selected"]
        return state

    if patient_id is None:
        # Demo mode: confirm without patient FK
        state["booking"] = {
            "slot_id":     selected_slot.get("slot_id"),
            "doctor_name": selected_slot.get("doctor_name"),
            "specialty":   selected_slot.get("specialty"),
            "date":        selected_slot.get("date"),
            "time":        selected_slot.get("time"),
            "patient_name": patient.get("name", "Guest"),
            "status":      "confirmed",
            "appointment_id": f"DEMO-{selected_slot.get('slot_id', 0)}",
        }
        state["step_results"] = state.get("step_results", {})
        state["step_results"]["confirm_booking"] = {"status": "confirmed_demo", **state["booking"]}
        print(f"[{AGENT_NAME}] Demo booking confirmed (slot {selected_slot.get('slot_id')})")
        return state

    confirmed = confirm_appointment(
        slot_id=selected_slot["slot_id"],
        patient_id=patient_id,
        reason=reason,
        workflow_id=workflow_id,
    )

    if confirmed:
        dt_val = confirmed["datetime"]
        if isinstance(dt_val, str):
            dt = datetime.fromisoformat(dt_val)
        else:
            dt = dt_val
        state["booking"] = {
            "appointment_id": confirmed["id"],
            "doctor_name":    selected_slot.get("doctor_name"),
            "specialty":      selected_slot.get("specialty"),
            "date":           dt.strftime("%A, %B %d, %Y"),
            "time":           dt.strftime("%I:%M %p"),
            "patient_name":   patient.get("name", ""),
            "status":         "confirmed",
        }
        state["step_results"] = state.get("step_results", {})
        state["step_results"]["confirm_booking"] = {"status": "confirmed", **state["booking"]}
        print(f"[{AGENT_NAME}] Appointment confirmed: ID {confirmed['id']}")
    else:
        state["errors"] = state.get("errors", []) + ["Slot no longer available"]
        print(f"[{AGENT_NAME}] Slot no longer available")

    return state


def run(state: dict) -> dict:
    if state.get("selected_slot"):
        return confirm(state)
    return find_slots(state)
