"""
Bulk enrollment from a folder structure.

HOW TO USE:
-----------
1. Create subfolders inside  enroll_images/  named as:
       FullName_EmployeeID
   Examples:
       enroll_images/Touqeer_001/
       enroll_images/Ahmed_002/
       enroll_images/Sara Khan_003/

2. Put 3-5 clear, front-facing photos in each subfolder.
   Supported formats: jpg, jpeg, png, bmp, webp

3. Run from the project root:
       venv/Scripts/python.exe scripts/enroll_from_folder.py

The script:
  - Detects faces in each photo
  - Extracts 512D ArcFace embeddings
  - Saves person + embeddings to Supabase
  - Skips people already enrolled (by employee_id)
  - Reports results at the end
"""

import os
import sys
import cv2
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Always resolve paths relative to project root (one level up from scripts/)
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

SUPABASE_URL   = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "")
ENROLL_DIR     = ROOT_DIR / os.getenv("ENROLL_IMAGES_DIR", "enroll_images")
MODEL_NAME     = os.getenv("INSIGHTFACE_MODEL", "buffalo_l")
IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY not set in .env")
        sys.exit(1)

    if not ENROLL_DIR.exists():
        print(f"ERROR: Folder '{ENROLL_DIR}' not found.")
        print("Create it and add subfolders like:  enroll_images/Touqeer_001/")
        sys.exit(1)

    print(f"Loading face engine ({MODEL_NAME})...")
    from insightface.app import FaceAnalysis
    engine = FaceAnalysis(name=MODEL_NAME, providers=["CPUExecutionProvider"])
    engine.prepare(ctx_id=-1, det_size=(640, 480))
    print("Face engine ready.\n")

    db = create_client(SUPABASE_URL, SUPABASE_KEY)

    existing = {
        r["employee_id"]
        for r in db.table("persons").select("employee_id").execute().data
    }

    results = []
    person_dirs = sorted([d for d in ENROLL_DIR.iterdir() if d.is_dir()])

    if not person_dirs:
        print(f"No subfolders found in '{ENROLL_DIR}'.")
        print("Create folders named  Name_EmployeeID  e.g.  Touqeer_001")
        sys.exit(0)

    for person_dir in person_dirs:
        folder_name = person_dir.name

        parts = folder_name.rsplit("_", 1)
        if len(parts) != 2:
            print(f"SKIP '{folder_name}' — folder name must be  Name_EmployeeID")
            results.append({"folder": folder_name, "status": "skipped (bad name)"})
            continue

        name, employee_id = parts[0].strip(), parts[1].strip()

        if employee_id in existing:
            print(f"SKIP '{name}' (ID: {employee_id}) — already enrolled")
            results.append({"folder": folder_name, "status": "already enrolled"})
            continue

        images = [f for f in person_dir.iterdir() if f.suffix.lower() in IMG_EXTENSIONS]
        if not images:
            print(f"SKIP '{name}' — no images found in {person_dir}")
            results.append({"folder": folder_name, "status": "no images"})
            continue

        print(f"Enrolling '{name}' (ID: {employee_id}) — {len(images)} image(s)...")

        try:
            row = db.table("persons").insert({
                "name": name,
                "employee_id": employee_id,
            }).execute()
            person_id = row.data[0]["id"]
        except Exception as e:
            print(f"  ERROR creating person: {e}")
            results.append({"folder": folder_name, "status": f"DB error: {e}"})
            continue

        added = 0
        for img_path in images:
            img = cv2.imread(str(img_path))
            if img is None:
                print(f"  SKIP {img_path.name} — cannot read")
                continue

            faces = engine.get(img)
            if not faces:
                print(f"  SKIP {img_path.name} — no face detected")
                continue

            face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
            embedding = face.normed_embedding

            try:
                db.table("embeddings").insert({
                    "person_id": person_id,
                    "embedding": embedding.tolist(),
                }).execute()
                added += 1
                print(f"  + {img_path.name}")
            except Exception as e:
                print(f"  ERROR saving embedding: {e}")

        if added == 0:
            db.table("persons").delete().eq("id", person_id).execute()
            status = "FAILED — no faces detected in any image"
        else:
            existing.add(employee_id)
            status = f"enrolled ({added} embeddings)"

        print(f"  -> {status}\n")
        results.append({"folder": folder_name, "name": name, "status": status})

    print("\n" + "="*50)
    print("ENROLLMENT SUMMARY")
    print("="*50)
    for r in results:
        print(f"  {r['folder']:30s}  {r['status']}")
    print("="*50)
    print("\nDone! Restart the server or call POST /reload-index to apply changes.")


if __name__ == "__main__":
    main()
