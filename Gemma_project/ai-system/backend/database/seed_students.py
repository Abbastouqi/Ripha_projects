"""
Seed sample Riphah student data into PostgreSQL.

Run once:
    python -m backend.database.seed_students

Safe to re-run — uses ON CONFLICT DO UPDATE (upsert).
"""

from backend.database.students_db import (
    create_student_tables,
    upsert_student,
    upsert_course,
    upsert_enrollment,
    upsert_attendance,
)

# ---------------------------------------------------------------------------
# Sample courses (shared across students)
# ---------------------------------------------------------------------------
COURSES = [
    {"code": "CS-301",  "name": "Data Structures & Algorithms",  "credit_hours": 3, "department": "Computer Science",    "instructor": "Dr. Tariq Mahmood"},
    {"code": "CS-302",  "name": "Operating Systems",             "credit_hours": 3, "department": "Computer Science",    "instructor": "Dr. Sana Ullah"},
    {"code": "CS-303",  "name": "Database Management Systems",   "credit_hours": 3, "department": "Computer Science",    "instructor": "Dr. Amna Khalid"},
    {"code": "CS-304",  "name": "Computer Networks",             "credit_hours": 3, "department": "Computer Science",    "instructor": "Mr. Fahad Ali"},
    {"code": "CS-305",  "name": "Software Engineering",          "credit_hours": 3, "department": "Computer Science",    "instructor": "Dr. Zara Ahmed"},
    {"code": "AI-401",  "name": "Machine Learning",              "credit_hours": 3, "department": "Artificial Intelligence", "instructor": "Dr. Hassan Raza"},
    {"code": "AI-402",  "name": "Deep Learning",                 "credit_hours": 3, "department": "Artificial Intelligence", "instructor": "Dr. Hassan Raza"},
    {"code": "AI-403",  "name": "Natural Language Processing",   "credit_hours": 3, "department": "Artificial Intelligence", "instructor": "Dr. Sadia Nawaz"},
    {"code": "EE-201",  "name": "Circuit Analysis",              "credit_hours": 3, "department": "Electrical Engineering",  "instructor": "Dr. Usman Ghani"},
    {"code": "EE-202",  "name": "Digital Logic Design",          "credit_hours": 3, "department": "Electrical Engineering",  "instructor": "Mr. Bilal Khan"},
    {"code": "MT-101",  "name": "Calculus & Analytical Geometry","credit_hours": 3, "department": "Mathematics",          "instructor": "Dr. Naila Riaz"},
    {"code": "MT-102",  "name": "Linear Algebra",                "credit_hours": 3, "department": "Mathematics",          "instructor": "Dr. Naila Riaz"},
    {"code": "IS-301",  "name": "Islamic Studies",               "credit_hours": 2, "department": "Islamic Studies",      "instructor": "Mufti Abdul Rauf"},
    {"code": "EN-101",  "name": "Communication Skills",          "credit_hours": 2, "department": "English",              "instructor": "Ms. Hina Shah"},
    {"code": "MBA-501", "name": "Strategic Management",          "credit_hours": 3, "department": "Business Administration", "instructor": "Dr. Kamran Nawaz"},
    {"code": "MBA-502", "name": "Financial Management",          "credit_hours": 3, "department": "Business Administration", "instructor": "Dr. Shafiq Ahmed"},
]

# ---------------------------------------------------------------------------
# Sample students
# ---------------------------------------------------------------------------
STUDENTS = [
    {
        "name": "Awais Khan",
        "reg_no": "RIU-2022-CS-001",
        "email": "awais.khan@riphah.edu.pk",
        "cnic": "35202-1234567-1",
        "department": "Computer Science",
        "program": "BS Computer Science",
        "semester": 6,
        "cgpa": 3.45,
        "status": "active",
        "campus": "Islamabad",
        "enrollment_year": 2022,
        "phone": "0300-1234567",
        "address": "House 12, Street 4, G-11/1, Islamabad",
        "father_name": "Aslam Khan",
    },
    {
        "name": "Sara Ahmed",
        "reg_no": "RIU-2021-CS-045",
        "email": "sara.ahmed@riphah.edu.pk",
        "cnic": "61101-9876543-2",
        "department": "Computer Science",
        "program": "BS Computer Science",
        "semester": 8,
        "cgpa": 3.82,
        "status": "active",
        "campus": "Islamabad",
        "enrollment_year": 2021,
        "phone": "0311-9876543",
        "address": "Flat 5, Block B, PWD Housing Scheme, Islamabad",
        "father_name": "Iftikhar Ahmed",
    },
    {
        "name": "Bilal Hussain",
        "reg_no": "RIU-2023-AI-012",
        "email": "bilal.hussain@riphah.edu.pk",
        "cnic": "42201-5678901-3",
        "department": "Artificial Intelligence",
        "program": "BS Artificial Intelligence",
        "semester": 4,
        "cgpa": 3.10,
        "status": "active",
        "campus": "Lahore",
        "enrollment_year": 2023,
        "phone": "0321-5678901",
        "address": "25-B, Model Town, Lahore",
        "father_name": "Tariq Hussain",
    },
    {
        "name": "Fatima Malik",
        "reg_no": "RIU-2022-EE-033",
        "email": "fatima.malik@riphah.edu.pk",
        "cnic": "38401-1122334-4",
        "department": "Electrical Engineering",
        "program": "BS Electrical Engineering",
        "semester": 6,
        "cgpa": 3.67,
        "status": "active",
        "campus": "Islamabad",
        "enrollment_year": 2022,
        "phone": "0333-1122334",
        "address": "House 7, Lane 3, Bahria Town Phase 4, Rawalpindi",
        "father_name": "Malik Irfan",
    },
    {
        "name": "Usman Tariq",
        "reg_no": "RIU-2020-MBA-007",
        "email": "usman.tariq@riphah.edu.pk",
        "cnic": "37405-4455667-5",
        "department": "Business Administration",
        "program": "MBA",
        "semester": 3,
        "cgpa": 3.25,
        "status": "active",
        "campus": "Islamabad",
        "enrollment_year": 2020,
        "phone": "0345-4455667",
        "address": "Street 9, F-8/2, Islamabad",
        "father_name": "Tariq Mehmood",
    },
]

# ---------------------------------------------------------------------------
# Enrollments & attendance for current semester
# (format: (student_reg_no, course_code, semester, year, grade, grade_pts, attended, total))
# ---------------------------------------------------------------------------
ENROLLMENTS = [
    # Awais — Semester 6 (CS)
    ("RIU-2022-CS-001", "CS-301", 6, 2024, "A",  4.00, 42, 45),
    ("RIU-2022-CS-001", "CS-302", 6, 2024, "B+", 3.50, 38, 45),
    ("RIU-2022-CS-001", "CS-303", 6, 2024, "A",  4.00, 44, 45),
    ("RIU-2022-CS-001", "CS-304", 6, 2024, "B",  3.00, 35, 45),
    ("RIU-2022-CS-001", "IS-301", 6, 2024, "A",  4.00, 28, 30),

    # Sara — Semester 8 (CS)
    ("RIU-2021-CS-045", "CS-305", 8, 2024, "A",  4.00, 43, 45),
    ("RIU-2021-CS-045", "AI-401", 8, 2024, "A",  4.00, 45, 45),
    ("RIU-2021-CS-045", "AI-402", 8, 2024, "A-", 3.70, 41, 45),
    ("RIU-2021-CS-045", "MT-102", 8, 2024, "B+", 3.50, 39, 45),

    # Bilal — Semester 4 (AI)
    ("RIU-2023-AI-012", "AI-401", 4, 2024, "B+", 3.50, 37, 45),
    ("RIU-2023-AI-012", "CS-303", 4, 2024, "B",  3.00, 36, 45),
    ("RIU-2023-AI-012", "MT-101", 4, 2024, "C+", 2.50, 30, 45),
    ("RIU-2023-AI-012", "EN-101", 4, 2024, "A",  4.00, 28, 30),

    # Fatima — Semester 6 (EE)
    ("RIU-2022-EE-033", "EE-201", 6, 2024, "A",  4.00, 44, 45),
    ("RIU-2022-EE-033", "EE-202", 6, 2024, "A",  4.00, 45, 45),
    ("RIU-2022-EE-033", "MT-102", 6, 2024, "A-", 3.70, 42, 45),
    ("RIU-2022-EE-033", "IS-301", 6, 2024, "A",  4.00, 29, 30),

    # Usman — Semester 3 (MBA)
    ("RIU-2020-MBA-007", "MBA-501", 3, 2024, "B+", 3.50, 38, 45),
    ("RIU-2020-MBA-007", "MBA-502", 3, 2024, "B",  3.00, 33, 45),
    ("RIU-2020-MBA-007", "EN-101", 3, 2024, "A",  4.00, 28, 30),
]


def run_seed() -> None:
    print("Creating student tables...")
    create_student_tables()

    print("Upserting courses...")
    course_id_map: dict[str, int] = {}
    for c in COURSES:
        cid = upsert_course(c)
        course_id_map[c["code"]] = cid
        print(f"  Course: {c['code']} — {c['name']} (id={cid})")

    print("Upserting students...")
    student_id_map: dict[str, int] = {}
    for s in STUDENTS:
        sid = upsert_student(s)
        student_id_map[s["reg_no"]] = sid
        print(f"  Student: {s['name']} ({s['reg_no']}) — id={sid}")

    print("Upserting enrollments & attendance...")
    for reg_no, code, sem, yr, grade, gp, attended, total in ENROLLMENTS:
        sid = student_id_map.get(reg_no)
        cid = course_id_map.get(code)
        if not sid or not cid:
            print(f"  [WARN] skipping {reg_no}/{code} — not found")
            continue
        upsert_enrollment({
            "student_id": sid, "course_id": cid,
            "semester": sem, "year": yr,
            "grade": grade, "grade_points": gp, "status": "completed",
        })
        upsert_attendance({
            "student_id": sid, "course_id": cid,
            "semester": sem, "year": yr,
            "total_classes": total, "attended": attended,
        })
        print(f"  Enrollment: {reg_no} -> {code}  grade={grade}  attendance={attended}/{total}")

    print("\nSeed complete.")
    print(f"  Students: {len(STUDENTS)}")
    print(f"  Courses:  {len(COURSES)}")
    print(f"  Records:  {len(ENROLLMENTS)}")


if __name__ == "__main__":
    run_seed()
