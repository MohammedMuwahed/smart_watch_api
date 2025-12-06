import json
import os
import traceback
import firebase_admin
from firebase_admin import credentials, db

KEY = "serviceAccountKey.json"
if not os.path.exists(KEY):
    raise SystemExit("serviceAccountKey.json missing")

cred = credentials.Certificate(KEY)
with open(KEY, "r", encoding="utf-8") as f:
    info = json.load(f)
project_id = info.get("project_id")
candidates = []

# If you already have a URL string you tried, add it here:
# candidates.append("https://smartwatch-university-project.firebaseio.com")

if project_id:
    candidates.append(f"https://{project_id}.firebaseio.com")
    candidates.append(f"https://{project_id}.firebasedatabase.app")

# Try plain google style (rare)
candidates.append(f"https://{project_id}-default-rtdb.firebaseio.com" if project_id else "")

candidates = [c for c in candidates if c]

print("RTDB candidates to test:")
for c in candidates:
    print(" -", c)

for url in candidates:
    print("\n--- Testing", url, "---")
    try:
        app = firebase_admin.initialize_app(cred, {"databaseURL": url}, name=url)
    except Exception as e_init:
        print("initialize_app failed:", repr(e_init))
        # try to continue by getting existing app with same name
        try:
            app = firebase_admin.get_app(name=url)
        except Exception:
            app = None

    try:
        ref = db.reference("/", app=app)
        root = ref.get()
        print("SUCCESS read root (type):", type(root).__name__)
        try:
            db.reference("/__diag_test__", app=app).set({"ok": True})
            print("SUCCESS write /__diag_test__")
            print("readback:", db.reference("/__diag_test__", app=app).get())
        except Exception as e_write:
            print("WRITE FAILED:", repr(e_write))
    except Exception as e:
        print("READ FAILED:", repr(e))
        traceback.print_exc()
    finally:
        # cleanup named app so next iteration can re-init
        try:
            firebase_admin.delete_app(app)
        except Exception:
            pass