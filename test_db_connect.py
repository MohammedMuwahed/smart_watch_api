import os
from firebase_admin import credentials, initialize_app, db

# Use your Realtime Database URL here (not the console URL)
#URL = "https://smartwatch-university-project.firebaseio.com"  # <- replace with the exact RTDB URL from the console
URL = "https://smartwatch-university-project.web.app"

if not os.path.exists("serviceAccountKey.json"):
    raise SystemExit("serviceAccountKey.json missing")

cred = credentials.Certificate("serviceAccountKey.json")
app = initialize_app(cred, {"databaseURL": URL})

try:
    root = db.reference("/").get()
    print("OK: root read (type):", type(root))
    db.reference("/test_temp").set({"ok": True})
    print("OK: write succeeded")
    print("test_temp ->", db.reference("/test_temp").get())
except Exception as e:
    print("ERROR:", repr(e))