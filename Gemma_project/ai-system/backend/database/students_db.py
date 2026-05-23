"""
Student records database layer.

Tables (auto-created on first import):
  students    — core student profile
  courses     — course catalogue
  enrollments — student ↔ course per semester (with grade)
  attendance  — per-course attendance per semester

All queries use the shared psycopg connection from db.py.
"""

from backend.database.db import get_cursor


# ---------------------------------------------------------------------------
# Schema bootstrap (called once from main.py lifespan)
# ---------------------------------------------------------------------------

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(100)  NOT NULL,
    reg_no           VARCHAR(50)   UNIQUE NOT NULL,
    email            VARCHAR(200)  UNIQUE,
    cnic             VARCHAR(20),
    department       VARCHAR(100),
    program          VARCHAR(100),
    semester         INTEGER       DEFAULT 1,
    cgpa             DECIMAL(3,2)  DEFAULT 0.00,
    status           VARCHAR(20)   DEFAULT 'active',
    campus           VARCHAR(50)   DEFAULT 'Islamabad',
    enrollment_year  INTEGER,
    phone            VARCHAR(20),
    address          TEXT,
    father_name      VARCHAR(100),
    created_at       TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
    id           SERIAL PRIMARY KEY,
    code         VARCHAR(20)  UNIQUE NOT NULL,
    name         VARCHAR(150) NOT NULL,
    credit_hours INTEGER      DEFAULT 3,
    department   VARCHAR(100),
    instructor   VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS enrollments (
    id           SERIAL PRIMARY KEY,
    student_id   INTEGER REFERENCES students(id)  ON DELETE CASCADE,
    course_id    INTEGER REFERENCES courses(id)    ON DELETE CASCADE,
    semester     INTEGER NOT NULL,
    year         INTEGER NOT NULL,
    grade        VARCHAR(5),
    grade_points DECIMAL(3,2),
    status       VARCHAR(20) DEFAULT 'enrolled',
    UNIQUE(student_id, course_id, semester, year)
);

CREATE TABLE IF NOT EXISTS attendance (
    id            SERIAL PRIMARY KEY,
    student_id    INTEGER REFERENCES students(id)  ON DELETE CASCADE,
    course_id     INTEGER REFERENCES courses(id)    ON DELETE CASCADE,
    semester      INTEGER NOT NULL,
    year          INTEGER NOT NULL,
    total_classes INTEGER DEFAULT 0,
    attended      INTEGER DEFAULT 0,
    percentage    DECIMAL(5,2) DEFAULT 0.00,
    UNIQUE(student_id, course_id, semester, year)
);
"""


def create_student_tables() -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(CREATE_TABLES_SQL)
    print("[StudentsDB] Tables verified / created.")


# ---------------------------------------------------------------------------
# Student queries
# ---------------------------------------------------------------------------

def get_student_by_name(name: str) -> dict | None:
    """Case-insensitive name search — returns first match."""
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM students WHERE LOWER(name) LIKE LOWER(%s) AND status != 'deleted'",
            (f"%{name}%",),
        )
        return cur.fetchone()


def get_student_by_reg(reg_no: str) -> dict | None:
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM students WHERE LOWER(reg_no) = LOWER(%s)", (reg_no,))
        return cur.fetchone()


def get_all_students(department: str | None = None, limit: int = 50) -> list:
    with get_cursor(commit=False) as cur:
        if department:
            cur.execute(
                "SELECT * FROM students WHERE LOWER(department) = LOWER(%s) "
                "AND status != 'deleted' ORDER BY name LIMIT %s",
                (department, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM students WHERE status != 'deleted' ORDER BY name LIMIT %s",
                (limit,),
            )
        return cur.fetchall()


def search_students(query: str) -> list:
    """Search by name, reg_no, or department (partial match)."""
    q = f"%{query}%"
    with get_cursor(commit=False) as cur:
        cur.execute(
            """SELECT * FROM students
               WHERE (LOWER(name) LIKE LOWER(%s)
                   OR LOWER(reg_no) LIKE LOWER(%s)
                   OR LOWER(department) LIKE LOWER(%s))
                 AND status != 'deleted'
               ORDER BY name LIMIT 10""",
            (q, q, q),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Enrollment & course queries
# ---------------------------------------------------------------------------

def get_student_courses(student_id: int, semester: int | None = None) -> list:
    """Return enrolled courses with grade info, optionally filtered by semester."""
    with get_cursor(commit=False) as cur:
        if semester:
            cur.execute(
                """SELECT c.code, c.name, c.credit_hours, c.instructor,
                          e.semester, e.year, e.grade, e.grade_points, e.status
                   FROM enrollments e
                   JOIN courses c ON c.id = e.course_id
                   WHERE e.student_id = %s AND e.semester = %s
                   ORDER BY c.code""",
                (student_id, semester),
            )
        else:
            cur.execute(
                """SELECT c.code, c.name, c.credit_hours, c.instructor,
                          e.semester, e.year, e.grade, e.grade_points, e.status
                   FROM enrollments e
                   JOIN courses c ON c.id = e.course_id
                   WHERE e.student_id = %s
                   ORDER BY e.year DESC, e.semester DESC, c.code""",
                (student_id,),
            )
        return cur.fetchall()


def get_student_attendance(student_id: int, semester: int | None = None) -> list:
    with get_cursor(commit=False) as cur:
        if semester:
            cur.execute(
                """SELECT c.code, c.name, a.semester, a.year,
                          a.total_classes, a.attended, a.percentage
                   FROM attendance a
                   JOIN courses c ON c.id = a.course_id
                   WHERE a.student_id = %s AND a.semester = %s
                   ORDER BY c.code""",
                (student_id, semester),
            )
        else:
            cur.execute(
                """SELECT c.code, c.name, a.semester, a.year,
                          a.total_classes, a.attended, a.percentage
                   FROM attendance a
                   JOIN courses c ON c.id = a.course_id
                   WHERE a.student_id = %s
                   ORDER BY a.year DESC, a.semester DESC, c.code""",
                (student_id,),
            )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Full profile (student + courses + attendance for current semester)
# ---------------------------------------------------------------------------

def get_student_full_profile(student_id: int) -> dict:
    student = None
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM students WHERE id = %s", (student_id,))
        student = cur.fetchone()
    if not student:
        return {}
    semester = student.get("semester", 1)
    courses    = get_student_courses(student_id, semester)
    attendance = get_student_attendance(student_id, semester)
    return {
        "student":    dict(student),
        "courses":    [dict(c) for c in courses],
        "attendance": [dict(a) for a in attendance],
    }


# ---------------------------------------------------------------------------
# Admin / seeding helpers
# ---------------------------------------------------------------------------

def upsert_student(data: dict) -> int:
    """Insert or update student by reg_no. Returns student id."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO students
               (name, reg_no, email, cnic, department, program, semester,
                cgpa, status, campus, enrollment_year, phone, address, father_name)
               VALUES (%(name)s, %(reg_no)s, %(email)s, %(cnic)s, %(department)s,
                       %(program)s, %(semester)s, %(cgpa)s, %(status)s, %(campus)s,
                       %(enrollment_year)s, %(phone)s, %(address)s, %(father_name)s)
               ON CONFLICT (reg_no) DO UPDATE SET
                   name=EXCLUDED.name, cgpa=EXCLUDED.cgpa,
                   semester=EXCLUDED.semester, status=EXCLUDED.status
               RETURNING id""",
            data,
        )
        return cur.fetchone()["id"]


def upsert_course(data: dict) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO courses (code, name, credit_hours, department, instructor)
               VALUES (%(code)s, %(name)s, %(credit_hours)s, %(department)s, %(instructor)s)
               ON CONFLICT (code) DO UPDATE SET
                   name=EXCLUDED.name, instructor=EXCLUDED.instructor
               RETURNING id""",
            data,
        )
        return cur.fetchone()["id"]


def upsert_enrollment(data: dict) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO enrollments
               (student_id, course_id, semester, year, grade, grade_points, status)
               VALUES (%(student_id)s, %(course_id)s, %(semester)s, %(year)s,
                       %(grade)s, %(grade_points)s, %(status)s)
               ON CONFLICT (student_id, course_id, semester, year) DO UPDATE SET
                   grade=EXCLUDED.grade, grade_points=EXCLUDED.grade_points""",
            data,
        )


def upsert_attendance(data: dict) -> None:
    pct = 0.0
    if data.get("total_classes", 0) > 0:
        pct = round(data["attended"] / data["total_classes"] * 100, 2)
    data["percentage"] = pct
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO attendance
               (student_id, course_id, semester, year, total_classes, attended, percentage)
               VALUES (%(student_id)s, %(course_id)s, %(semester)s, %(year)s,
                       %(total_classes)s, %(attended)s, %(percentage)s)
               ON CONFLICT (student_id, course_id, semester, year) DO UPDATE SET
                   total_classes=EXCLUDED.total_classes,
                   attended=EXCLUDED.attended,
                   percentage=EXCLUDED.percentage""",
            data,
        )
