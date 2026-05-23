AGENT_NAME = "ui_agent"


def _format_slots(slots: list[dict]) -> str:
    if not slots:
        return "No available slots found. Please try a different specialty or date range."
    lines = ["Here are the available appointment slots:\n"]
    for i, slot in enumerate(slots, 1):
        name = slot['doctor_name']
        if not name.startswith("Dr."):
            name = f"Dr. {name}"
        lines.append(
            f"  Option {i}: {name} ({slot['specialty'].title()})\n"
            f"             {slot['date']} at {slot['time']}\n"
            f"             Slot ID: {slot['slot_id']}"
        )
    lines.append("\nPlease select an option to confirm your appointment.")
    return "\n".join(lines)


def _format_booking(booking: dict) -> str:
    return (
        f"Your appointment has been successfully booked!\n\n"
        f"  Doctor:         {booking.get('doctor_name', 'N/A')}\n"
        f"  Specialty:      {booking.get('specialty', 'N/A').title()}\n"
        f"  Date & Time:    {booking.get('date', 'N/A')} at {booking.get('time', 'N/A')}\n"
        f"  Confirmation #: {booking.get('appointment_id', 'N/A')}\n\n"
        f"A confirmation has been sent to your registered contact details."
    )


def run(state: dict) -> dict:
    print(f"[{AGENT_NAME}] Formatting output for patient...")

    output_parts = []
    step_results = state.get("step_results", {})

    if "verify_patient" in step_results:
        auth = step_results["verify_patient"]
        if auth.get("status") == "verified":
            output_parts.append(f"Welcome back, {auth.get('name', 'Patient')}!")
        else:
            output_parts.append(f"Welcome! Proceeding as guest session.")

    if state.get("no_specialist_notice"):
        output_parts.append(f"Note: {state['no_specialist_notice']}")

    if state.get("available_slots") and not state.get("selected_slot"):
        output_parts.append(_format_slots(state["available_slots"]))

    if state.get("booking"):
        output_parts.append(_format_booking(state["booking"]))

    if state.get("errors"):
        output_parts.append(f"Note: {'; '.join(state['errors'])}")

    formatted = "\n\n".join(output_parts) if output_parts else "Processing your request..."
    state["ui_output"] = formatted
    state["step_results"] = step_results
    state["step_results"]["present_options"] = {
        "status": "ok",
        "output_preview": formatted[:100],
    }
    print(f"[{AGENT_NAME}] Output formatted")
    return state
