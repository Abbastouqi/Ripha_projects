from backend.database.db import get_patient_by_name, get_patient_by_id
from backend.rag.retriever import retrieve_policies

AGENT_NAME = "auth_agent"


def run(state: dict) -> dict:
    print(f"[{AGENT_NAME}] Verifying patient identity...")
    patient_name = state.get("patient_name", "")
    patient_id = state.get("patient_id")

    patient = None
    try:
        if patient_id:
            patient = get_patient_by_id(int(patient_id))
        if not patient and patient_name:
            patient = get_patient_by_name(patient_name)
    except Exception as e:
        print(f"[{AGENT_NAME}] DB unavailable: {e}. Proceeding as guest.")

    if not patient:
        # Create a minimal guest profile so the demo still works
        print(f"[{AGENT_NAME}] Patient '{patient_name}' not found, creating guest session")
        state["patient"] = {
            "id": None,
            "name": patient_name or "Guest",
            "email": "",
            "phone": "",
            "insurance_id": "GUEST",
        }
        state["auth_status"] = "guest"
        state["step_results"] = state.get("step_results", {})
        state["step_results"]["verify_patient"] = {
            "status": "guest",
            "message": f"Patient '{patient_name}' not found in system. Proceeding as guest.",
        }
    else:
        print(f"[{AGENT_NAME}] Patient verified: {patient['name']}")
        state["patient"] = dict(patient)
        state["patient_id"] = patient["id"]
        state["auth_status"] = "verified"
        state["step_results"] = state.get("step_results", {})
        state["step_results"]["verify_patient"] = {
            "status": "verified",
            "patient_id": patient["id"],
            "name": patient["name"],
            "insurance_id": patient.get("insurance_id"),
        }

    return state
