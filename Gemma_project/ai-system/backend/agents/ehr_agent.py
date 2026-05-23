from datetime import datetime
from backend.database.db import get_patient_appointments

AGENT_NAME = "ehr_agent"


def run(state: dict) -> dict:
    print(f"[{AGENT_NAME}] Reading patient EHR...")
    patient = state.get("patient", {})
    patient_id = patient.get("id") or state.get("patient_id")

    if not patient_id:
        state["ehr_summary"] = "No prior medical records found (guest session)."
        state["step_results"] = state.get("step_results", {})
        state["step_results"]["update_ehr"] = {"status": "skipped", "reason": "guest_session"}
        return state

    try:
        history = get_patient_appointments(patient_id)
    except Exception as e:
        print(f"[{AGENT_NAME}] DB unavailable: {e}")
        state["ehr_summary"] = "EHR unavailable (database offline)."
        state["step_results"] = state.get("step_results", {})
        state["step_results"]["update_ehr"] = {"status": "skipped", "reason": "db_unavailable"}
        return state

    if not history:
        summary = f"Patient {patient.get('name', '')} has no prior appointment history."
    else:
        lines = [f"Patient: {patient.get('name', '')} (ID: {patient_id})"]
        lines.append(f"Insurance: {patient.get('insurance_id', 'N/A')}")
        lines.append("\nAppointment History:")
        for appt in history[:5]:
            dt_val = appt["datetime"]
            if isinstance(dt_val, str):
                dt = datetime.fromisoformat(dt_val)
            else:
                dt = dt_val
            lines.append(
                f"  - {dt.strftime('%Y-%m-%d')} | Dr. {appt['doctor_name']} ({appt['specialty']}) "
                f"| Status: {appt['status']} | Reason: {appt.get('reason', 'N/A')}"
            )
        summary = "\n".join(lines)

    state["ehr_summary"] = summary
    state["step_results"] = state.get("step_results", {})
    state["step_results"]["update_ehr"] = {
        "status": "ok",
        "records_found": len(history),
        "summary": summary[:200],
    }
    print(f"[{AGENT_NAME}] EHR summary generated ({len(history)} records)")
    return state
