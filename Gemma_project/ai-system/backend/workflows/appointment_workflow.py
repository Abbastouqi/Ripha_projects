import os
import json
import uuid
from typing import TypedDict, Optional, Any
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class WorkflowState(TypedDict, total=False):
    workflow_id:       str
    patient_name:      str
    patient_id:        Optional[int]
    patient:           dict
    specialty:         str
    urgency:           str
    symptoms:          list
    task_type:         str
    auth_status:       str
    available_slots:   list
    selected_slot:     Optional[dict]
    booking:           dict
    ehr_summary:       str
    ui_output:         str
    notification_sent: bool
    step_results:      dict
    errors:            list
    status:            str
    awaiting_input:    str


# ---------------------------------------------------------------------------
# Graph builder — compatible with LangGraph 1.x
# ---------------------------------------------------------------------------

def build_graph():
    from langgraph.graph import StateGraph, END, START

    from backend.agents import auth_agent, schedule_agent, ehr_agent, notify_agent, ui_agent

    def _needs_slot_selection(state: WorkflowState) -> str:
        if not state.get("selected_slot") and state.get("available_slots"):
            return "wait_for_input"
        return "confirm"

    def _check_errors(state: WorkflowState) -> str:
        if state.get("errors"):
            return "error_end"
        return "continue"

    def _error_node(state: WorkflowState) -> WorkflowState:
        state["status"] = "error"
        return state

    def _wait_node(state: WorkflowState) -> WorkflowState:
        state["awaiting_input"] = "slot_selection"
        state["status"] = "awaiting_input"
        return state

    builder = StateGraph(WorkflowState)

    # Add nodes
    builder.add_node("verify_patient",    auth_agent.run)
    builder.add_node("find_slots",        schedule_agent.find_slots)
    builder.add_node("present_options",   ui_agent.run)
    builder.add_node("wait_for_input",    _wait_node)
    builder.add_node("confirm_booking",   schedule_agent.confirm)
    builder.add_node("update_ehr",        ehr_agent.run)
    builder.add_node("send_confirmation", notify_agent.run)
    builder.add_node("error_end",         _error_node)

    # Entry point
    builder.add_edge(START, "verify_patient")

    # Linear edges
    builder.add_edge("verify_patient", "find_slots")
    builder.add_edge("find_slots",     "present_options")

    # Conditional: wait for slot input or proceed directly to confirm
    builder.add_conditional_edges(
        "present_options",
        _needs_slot_selection,
        {"wait_for_input": "wait_for_input", "confirm": "confirm_booking"},
    )
    builder.add_edge("wait_for_input", END)

    # Conditional: error or continue after confirm
    builder.add_conditional_edges(
        "confirm_booking",
        _check_errors,
        {"error_end": "error_end", "continue": "update_ehr"},
    )
    builder.add_edge("update_ehr",        "send_confirmation")
    builder.add_edge("send_confirmation", END)
    builder.add_edge("error_end",         END)

    return builder.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_workflow(intent_json: dict, patient_name: str = "") -> dict:
    workflow_id = f"WF-{uuid.uuid4().hex[:8].upper()}"

    initial_state: WorkflowState = {
        "workflow_id":       workflow_id,
        "patient_name":      patient_name,
        "patient_id":        intent_json.get("patient_id"),
        "patient":           {},
        "specialty":         intent_json.get("specialty", "general"),
        "urgency":           intent_json.get("urgency", "routine"),
        "symptoms":          intent_json.get("symptoms", []),
        "task_type":         intent_json.get("task_type", "appointment_booking"),
        "auth_status":       "",
        "available_slots":   [],
        "selected_slot":     None,
        "booking":           {},
        "ehr_summary":       "",
        "ui_output":         "",
        "notification_sent": False,
        "step_results":      {},
        "errors":            [],
        "status":            "started",
        "awaiting_input":    "",
    }

    graph = _get_graph()
    result = dict(graph.invoke(initial_state, config={"recursion_limit": 25}))
    result["workflow_id"] = workflow_id

    if result.get("awaiting_input") == "slot_selection":
        result["status"] = "awaiting_input"
    elif result.get("errors"):
        result["status"] = "error"
    else:
        result["status"] = "completed"

    return result


def resume_workflow(state: dict, selected_slot: dict) -> dict:
    resume_state = dict(state)
    resume_state["selected_slot"]   = selected_slot
    resume_state["awaiting_input"]  = ""
    resume_state["status"]          = "running"

    # Re-invoke graph — it will skip straight to confirm since selected_slot is set
    from backend.agents import schedule_agent, ehr_agent, notify_agent

    result = dict(resume_state)
    result = schedule_agent.confirm(result)
    result = ehr_agent.run(result)
    result = notify_agent.run(result)

    if result.get("errors"):
        result["status"] = "error"
    else:
        result["status"] = "completed"

    result["workflow_id"] = state.get("workflow_id", "WF-000")
    return result
