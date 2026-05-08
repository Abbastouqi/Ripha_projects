import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL        = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY        = os.getenv("SUPABASE_KEY", "")
SIMILARITY_THRESHOLD  = float(os.getenv("SIMILARITY_THRESHOLD", "0.50"))
CAMERA_ID             = int(os.getenv("CAMERA_ID", "0"))
FRAME_SKIP            = int(os.getenv("FRAME_SKIP", "5"))
COOLDOWN_SECONDS      = int(os.getenv("COOLDOWN_SECONDS", "300"))
INSIGHTFACE_MODEL     = os.getenv("INSIGHTFACE_MODEL", "buffalo_l")   # ResNet100+ArcFace
EMBEDDING_DIM         = 512
CHECKOUT_TIMEOUT_SEC  = int(os.getenv("CHECKOUT_TIMEOUT_SEC", "300"))  # 5 min absent = checkout
ENROLL_IMAGES_DIR     = os.getenv("ENROLL_IMAGES_DIR", "enroll_images")
