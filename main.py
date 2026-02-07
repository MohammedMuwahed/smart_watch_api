import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi.middleware.cors import CORSMiddleware

# Firestore initialization (safe)
_firestore_client = None
_firebase_available = False
if os.path.exists("serviceAccountKey.json"):
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        _firestore_client = firestore.client()
        _firebase_available = True
        print("[INFO] Firestore initialized")
    except Exception as e:
        print(f"[WARN] Firestore init failed: {e}")
else:
    print("[WARN] serviceAccountKey.json not found. Firestore disabled for this process.")

# Document paths (Firestore)
DOC_STATE = "state/update"          # document path
DOC_DEVICE_LIGHTS = "device/lights"
DOC_DEVICE_CURTAIN = "device/curtain"

app = FastAPI(
    title="Smartwatch Automation API",
    description="Controls curtain + light state based on sleeping status (Firestore backend).",
    version="1.0",
)

# Allow CORS (set ALLOWED_ORIGINS env var to comma-separated list, default "*")
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
if _allowed_origins.strip() == "*":
    origins = ["*"]
else:
    origins = [o.strip() for o in _allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- MODELS ----------------
class SleepState(BaseModel):
    isSleeping: bool


class DeviceSettingUpdate(BaseModel):
    device: str  # 'lights' or 'curtain'
    setting: str  # 'sleepingStatus' or 'notSleepingStatus'
    value: bool


# ---------------- HELPERS ----------------
def _ensure_device_doc(ref):
    doc = ref.get()
    if not doc.exists:
        default = {"sleepingStatus": False, "notSleepingStatus": True, "active": False}
        ref.set(default)
        return default
    return doc.to_dict()


def update_device_states(is_sleeping: bool):
    """
    Reads device docs (sleepingStatus / notSleepingStatus) from Firestore
    and updates the 'active' field for both lights and curtain.
    """
    if not _firebase_available:
        raise HTTPException(status_code=503, detail="Firestore not initialized on server.")

    try:
        lights_ref = _firestore_client.document(DOC_DEVICE_LIGHTS)
        curtain_ref = _firestore_client.document(DOC_DEVICE_CURTAIN)

        lights = _ensure_device_doc(lights_ref)
        curtain = _ensure_device_doc(curtain_ref)

        if is_sleeping:
            new_light_state = lights.get("sleepingStatus")
            new_curtain_state = curtain.get("sleepingStatus")
        else:
            new_light_state = lights.get("notSleepingStatus")
            new_curtain_state = curtain.get("notSleepingStatus")

        if new_light_state is None or new_curtain_state is None:
            raise HTTPException(status_code=400, detail="Device configuration missing required fields.")

        lights_ref.update({"active": new_light_state})
        curtain_ref.update({"active": new_curtain_state})

        return {"lights_active": new_light_state, "curtain_active": new_curtain_state}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Firestore error: {e}")


# ---------------- ENDPOINTS ----------------
@app.post("/update-sleep")
def set_sleep_status(state: SleepState):
    """
    Called by hardware (or app). Updates:
    - state/update (Firestore doc) → isSleeping
    - device/lights.active and device/curtain.active according to settings
    """
    if not _firebase_available:
        raise HTTPException(status_code=503, detail="Firestore not initialized on server.")

    try:
        # 1) Update global state doc
        state_ref = _firestore_client.document(DOC_STATE)
        state_ref.set({"isSleeping": state.isSleeping}, merge=True)

        # 2) Update devices according to rules
        result = update_device_states(state.isSleeping)

        return {"message": "State updated successfully", "isSleeping": state.isSleeping, "updated_device_states": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update sleep state: {e}")


@app.post("/device/update-setting")
def update_device_setting(update: DeviceSettingUpdate):
    """
    Called by the app when the user toggles a setting.
    Updates device/{device}.{setting} and preserves other fields.
    """
    if not _firebase_available:
        raise HTTPException(status_code=503, detail="Firestore not initialized on server.")

    device = update.device
    setting = update.setting
    value = update.value

    if device not in ("lights", "curtain"):
        raise HTTPException(status_code=400, detail="Invalid device. Must be 'lights' or 'curtain'.")

    if setting not in ("sleepingStatus", "notSleepingStatus"):
        raise HTTPException(status_code=400, detail="Invalid setting. Must be 'sleepingStatus' or 'notSleepingStatus'.")

    try:
        ref = _firestore_client.document(f"device/{device}")
        # ensure document exists
        _ensure_device_doc(ref)
        # update single field
        ref.update({setting: value})
        return {"message": "Device setting updated", "device": device, "setting": setting, "value": value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update device setting: {e}")


@app.get("/")
def root():
    return {"ok": True, "service": "smartwatch-automation", "firebase_available": _firebase_available}


@app.get("/debug/db")
def debug_db():
    if not _firebase_available:
        raise HTTPException(status_code=503, detail="Firestore not initialized")
    try:
        state_doc = _firestore_client.document(DOC_STATE).get()
        lights_doc = _firestore_client.document(DOC_DEVICE_LIGHTS).get()
        curtain_doc = _firestore_client.document(DOC_DEVICE_CURTAIN).get()
        return {
            "state": state_doc.to_dict() if state_doc.exists else None,
            "lights": lights_doc.to_dict() if lights_doc.exists else None,
            "curtain": curtain_doc.to_dict() if curtain_doc.exists else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB read failed: {e}")

# ---------------- NEW: GET SETTINGS ----------------
@app.get("/device/settings/sleep")
def get_sleep_settings():
    """
    Return the configured 'sleepingStatus' for lights and curtain.
    """
    if not _firebase_available:
        raise HTTPException(status_code=503, detail="Firestore not initialized")
    try:
        lights_doc = _firestore_client.document(DOC_DEVICE_LIGHTS).get()
        curtain_doc = _firestore_client.document(DOC_DEVICE_CURTAIN).get()

        lights = lights_doc.to_dict() if lights_doc.exists else {}
        curtain = curtain_doc.to_dict() if curtain_doc.exists else {}

        return {
            "lights": {"sleepingStatus": lights.get("sleepingStatus")},
            "curtain": {"sleepingStatus": curtain.get("sleepingStatus")}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read sleep settings: {e}")


@app.get("/device/settings/not-sleep")
def get_not_sleep_settings():
    """
    Return the configured 'notSleepingStatus' for lights and curtain.
    """
    if not _firebase_available:
        raise HTTPException(status_code=503, detail="Firestore not initialized")
    try:
        lights_doc = _firestore_client.document(DOC_DEVICE_LIGHTS).get()
        curtain_doc = _firestore_client.document(DOC_DEVICE_CURTAIN).get()

        lights = lights_doc.to_dict() if lights_doc.exists else {}
        curtain = curtain_doc.to_dict() if curtain_doc.exists else {}

        return {
            "lights": {"notSleepingStatus": lights.get("notSleepingStatus")},
            "curtain": {"notSleepingStatus": curtain.get("notSleepingStatus")}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read not-sleep settings: {e}")


@app.get("/state")
def get_state():
    """
    Return current global sleep state document.
    """
    if not _firebase_available:
        raise HTTPException(status_code=503, detail="Firestore not initialized")
    try:
        doc = _firestore_client.document(DOC_STATE).get()
        if doc.exists:
            data = doc.to_dict()
            return {"isSleeping": data.get("isSleeping")}
        return {"isSleeping": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read state: {e}")


@app.get("/state/is-sleeping")
def get_is_sleeping():
    """
    Convenience endpoint returning only the boolean or null if missing.
    """
    if not _firebase_available:
        raise HTTPException(status_code=503, detail="Firestore not initialized")
    try:
        doc = _firestore_client.document(DOC_STATE).get()
        if doc.exists:
            return {"isSleeping": bool(doc.to_dict().get("isSleeping"))}
        return {"isSleeping": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read isSleeping: {e}")