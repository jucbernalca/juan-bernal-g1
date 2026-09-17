import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_API_BASE_URL = os.getenv("GLM_API_BASE_URL", "http://149.232.135.126:4000/v1")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-5.2")
GLM_TIMEOUT = int(os.getenv("GLM_TIMEOUT", "30"))
GLM_MAX_RETRIES = int(os.getenv("GLM_MAX_RETRIES", "3"))
GLM_TEMPERATURE = float(os.getenv("GLM_TEMPERATURE", "0.1"))
GLM_MAX_TOKENS = int(os.getenv("GLM_MAX_TOKENS", "1024"))

ABSTENTION_THRESHOLD = float(os.getenv("ABSTENTION_THRESHOLD", "0.60"))

MAJOR_INCIDENT_MIN_TICKETS = int(os.getenv("MAJOR_INCIDENT_MIN_TICKETS", "5"))
MAJOR_INCIDENT_WINDOW_MINUTES = int(os.getenv("MAJOR_INCIDENT_WINDOW_MINUTES", "10"))

MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "5"))
RATE_LIMIT_RPS = float(os.getenv("RATE_LIMIT_RPS", "2.0"))

DATA_DIR = BASE_DIR / "data"
TICKETS_SAMPLE_PATH = DATA_DIR / "tickets_sample.json"

PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}

VALID_CATEGORIES = [
    "Cuenta y acceso",
    "Facturacion",
    "Disponibilidad y rendimiento",
    "Integraciones",
    "Datos y exportacion",
    "Solicitud de funcion",
    "Seguridad",
    "Otro",
]

VALID_PRIORITIES = ["P1", "P2", "P3", "P4"]

VALID_SENTIMENTS = ["positivo", "neutral", "negativo", "frustrado", "preocupado"]
