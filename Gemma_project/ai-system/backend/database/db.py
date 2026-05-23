import os
from contextlib import contextmanager
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

load_dotenv()

DB_CONFIG = {
    "host":            os.getenv("POSTGRES_HOST", "localhost"),
    "port":            int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":          os.getenv("POSTGRES_DB", "medical_ai"),
    "user":            os.getenv("POSTGRES_USER", "admin"),
    "password":        os.getenv("POSTGRES_PASSWORD", "admin123"),
    "connect_timeout": 3,
}


def get_connection():
    return psycopg.connect(**DB_CONFIG, row_factory=dict_row)


@contextmanager
def get_cursor(commit: bool = True):
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def get_patient_by_name(name: str) -> dict | None:
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM patients WHERE LOWER(name) = LOWER(%s)", (name,)
        )
        return cur.fetchone()


def get_patient_by_id(patient_id: int) -> dict | None:
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
        return cur.fetchone()


def get_doctors_by_specialty(specialty: str) -> list:
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM doctors WHERE LOWER(specialty) = LOWER(%s)", (specialty,)
        )
        return cur.fetchall()


def get_all_doctors() -> list:
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM doctors")
        return cur.fetchall()


def get_available_slots(doctor_id: int, limit: int = 5) -> list:
    with get_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT a.id, a.datetime, d.name AS doctor_name, d.specialty
            FROM appointments a
            JOIN doctors d ON d.id = a.doctor_id
            WHERE a.doctor_id = %s AND a.status = 'available' AND a.datetime > NOW()
            ORDER BY a.datetime
            LIMIT %s
            """,
            (doctor_id, limit),
        )
        return cur.fetchall()


def get_available_slots_by_specialty(specialty: str, limit: int = 3) -> list:
    with get_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT a.id, a.datetime, d.name AS doctor_name, d.specialty, d.id AS doctor_id
            FROM appointments a
            JOIN doctors d ON d.id = a.doctor_id
            WHERE LOWER(d.specialty) = LOWER(%s)
              AND a.status = 'available'
              AND a.datetime > NOW()
            ORDER BY a.datetime
            LIMIT %s
            """,
            (specialty, limit),
        )
        return cur.fetchall()


def confirm_appointment(
    slot_id: int, patient_id: int, reason: str, workflow_id: str
) -> dict | None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE appointments
            SET status = 'confirmed', patient_id = %s, reason = %s, workflow_id = %s
            WHERE id = %s AND status = 'available'
            RETURNING *
            """,
            (patient_id, reason, workflow_id, slot_id),
        )
        return cur.fetchone()


def get_patient_appointments(patient_id: int) -> list:
    with get_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT a.id, a.datetime, a.status, a.reason,
                   d.name AS doctor_name, d.specialty
            FROM appointments a
            JOIN doctors d ON d.id = a.doctor_id
            WHERE a.patient_id = %s
            ORDER BY a.datetime DESC
            """,
            (patient_id,),
        )
        return cur.fetchall()


def create_workflow(workflow_id: str, patient_id: int | None, task_type: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO workflows (id, patient_id, task_type, status, steps_json)
            VALUES (%s, %s, %s, 'started', '[]')
            ON CONFLICT (id) DO NOTHING
            """,
            (workflow_id, patient_id, task_type),
        )


def update_workflow(workflow_id: str, status: str, steps_json: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE workflows
            SET status = %s, steps_json = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (status, steps_json, workflow_id),
        )


def get_workflow(workflow_id: str) -> dict | None:
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM workflows WHERE id = %s", (workflow_id,))
        return cur.fetchone()


def log_notification(
    patient_id: int, workflow_id: str, notif_type: str, recipient: str, message: str
) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO notifications (patient_id, workflow_id, type, recipient, message)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (patient_id, workflow_id, notif_type, recipient, message),
        )


# ---------------------------------------------------------------------------
# Chat session management
# ---------------------------------------------------------------------------

def create_session(session_id: str, title: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO chat_sessions (id, title)
            VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (session_id, title[:200]),
        )


def get_sessions() -> list:
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT id, title, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC LIMIT 50"
        )
        return cur.fetchall()


def get_session_messages(session_id: str) -> list:
    with get_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, role, content, workflow, sources_json, created_at
            FROM chat_messages
            WHERE session_id = %s
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        return cur.fetchall()


def add_message(
    session_id: str,
    role: str,
    content: str,
    workflow: str = "general",
    sources: list | None = None,
) -> dict:
    import json as _json
    sources_json = _json.dumps(sources or [])
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO chat_messages (session_id, role, content, workflow, sources_json)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, role, content, workflow, sources_json, created_at
            """,
            (session_id, role, content, workflow, sources_json),
        )
        row = cur.fetchone()
        # Update session timestamp
        cur.execute(
            "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s",
            (session_id,),
        )
        return dict(row)


def delete_session(session_id: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))


def update_session_title(session_id: str, title: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE chat_sessions SET title = %s WHERE id = %s",
            (title[:200], session_id),
        )


# ---------------------------------------------------------------------------
# Uploaded documents registry
# ---------------------------------------------------------------------------

def save_document_record(doc_id: str, filename: str, file_type: str, chunks: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO uploaded_documents (id, filename, file_type, chunks_count)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET chunks_count = %s
            """,
            (doc_id, filename, file_type, chunks, chunks),
        )


def get_documents() -> list:
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT id, filename, file_type, chunks_count, created_at FROM uploaded_documents ORDER BY created_at DESC"
        )
        return cur.fetchall()


def delete_document_record(doc_id: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM uploaded_documents WHERE id = %s", (doc_id,))


# ---------------------------------------------------------------------------
# User management (auth)
# ---------------------------------------------------------------------------

def create_user(username: str, email: str, password_hash: str, role: str = "user") -> dict:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO users (username, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            RETURNING id, username, email, role, is_active, created_at
            """,
            (username, email, password_hash, role),
        )
        return dict(cur.fetchone())


def get_user_by_email(email: str) -> dict | None:
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(%s)", (email,))
        return cur.fetchone()


def get_user_by_id(user_id: int) -> dict | None:
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def get_all_users() -> list:
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT id, username, email, role, is_active, created_at FROM users ORDER BY created_at DESC"
        )
        return cur.fetchall()


def update_user_role(user_id: int, role: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))


def toggle_user_active(user_id: int, is_active: bool) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET is_active = %s WHERE id = %s", (is_active, user_id))


def delete_user_by_id(user_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))


def get_system_stats() -> dict:
    import json as _json
    stats: dict = {}
    with get_cursor(commit=False) as cur:
        for key, query in [
            ("total_users",             "SELECT COUNT(*) AS c FROM users"),
            ("total_sessions",          "SELECT COUNT(*) AS c FROM chat_sessions"),
            ("total_messages",          "SELECT COUNT(*) AS c FROM chat_messages"),
            ("confirmed_appointments",  "SELECT COUNT(*) AS c FROM appointments WHERE status = 'confirmed'"),
            ("uploaded_documents",      "SELECT COUNT(*) AS c FROM uploaded_documents"),
        ]:
            cur.execute(query)
            row = cur.fetchone()
            stats[key] = row["c"] if row else 0
    return stats


def get_all_appointments() -> list:
    with get_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT a.id, a.status, a.reason, a.datetime, a.workflow_id,
                   d.name AS doctor_name, d.specialty,
                   p.name AS patient_name
            FROM appointments a
            JOIN doctors d ON d.id = a.doctor_id
            LEFT JOIN patients p ON p.id = a.patient_id
            ORDER BY a.datetime DESC
            LIMIT 100
            """
        )
        return cur.fetchall()
