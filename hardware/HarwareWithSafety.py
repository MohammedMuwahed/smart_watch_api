import os
import time
import json

# ================= GPIO SETUP (REAL OR MOCK) =================
try:
    import RPi.GPIO as GPIO
except Exception:
    try:
        from RPi import GPIO
    except Exception:
        class _DummyPWM:
            def __init__(self, pin, freq): pass
            def start(self, d): pass
            def ChangeDutyCycle(self, d): pass
            def stop(self): pass

        class _MockGPIO:
            BCM = "BCM"; OUT = "OUT"; LOW = 0; HIGH = 1
            def setmode(self, m): print("[MOCK GPIO] setmode", m)
            def setwarnings(self, f): pass
            def setup(self, p, m): print(f"[MOCK GPIO] setup {p} {m}")
            def output(self, p, v): print(f"[MOCK GPIO] output {p} -> {v}")
            def PWM(self, p, f): return _DummyPWM(p, f)
            def cleanup(self): print("[MOCK GPIO] cleanup")
        GPIO = _MockGPIO()

# ================= HTTP SETUP =================
try:
    import requests
except Exception:
    requests = None
    import urllib.request
    import urllib.error

SERVER_BASE = os.environ.get(
    "SMART_SERVER_URL", "http://127.0.0.1:8000"
).strip().rstrip("/")

# ================= PINS =================
LAMP_PIN = 17
SERVO_PIN = 18

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(LAMP_PIN, GPIO.OUT)
GPIO.setup(SERVO_PIN, GPIO.OUT)

servo = GPIO.PWM(SERVO_PIN, 50)
servo.start(0)

# ================= HARDWARE ACTIONS =================
def turn_off_lamp():
    GPIO.output(LAMP_PIN, GPIO.LOW)
    print("[HW] Lamp -> OFF")

def turn_on_lamp():
    GPIO.output(LAMP_PIN, GPIO.HIGH)
    print("[HW] Lamp -> ON")

def activate_servo(action):
    """
    Continuous servo control:
    - close : clockwise
    - open  : counter-clockwise
    """
    duty = 7.5

    if action == "close":
        print("[HW] Curtain -> CLOSE")
        duty = 2.5
    elif action == "open":
        print("[HW] Curtain -> OPEN")
        duty = 12.5

    try:
        servo.ChangeDutyCycle(duty)
        time.sleep(3)
        servo.ChangeDutyCycle(7.5)
        time.sleep(0.2)
        servo.ChangeDutyCycle(0)
    except Exception as e:
        print(f"[WARN] Servo error: {e}")

# ================= SERVER COMMUNICATION =================
def _post_update_sleep(is_sleeping):
    url = f"{SERVER_BASE}/update-sleep"
    payload = {"isSleeping": bool(is_sleeping)}
    try:
        if requests:
            requests.post(url, json=payload, timeout=5)
        else:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[WARN] POST failed: {e}")

def _get_settings(endpoint):
    url = f"{SERVER_BASE}{endpoint}"
    try:
        if requests:
            r = requests.get(url, timeout=5)
            return r.json()
        else:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return json.load(resp)
    except Exception as e:
        print(f"[WARN] GET failed: {e}")
        return None

# ================= EVENT HANDLERS =================
def handle_sleep_event():
    print("[EVENT] Sleep detected")
    _post_update_sleep(True)

    cfg = _get_settings("/device/settings/sleep")
    if not cfg:
        return

    if cfg.get("lights", {}).get("sleepingStatus") is True:
        turn_off_lamp()

    if cfg.get("curtain", {}).get("sleepingStatus") is True:
        activate_servo("close")

def handle_wake_event():
    print("[EVENT] Wake detected")
    _post_update_sleep(False)

    cfg = _get_settings("/device/settings/not-sleep")
    if not cfg:
        return

    if cfg.get("lights", {}).get("notSleepingStatus") is True:
        turn_on_lamp()

    if cfg.get("curtain", {}).get("notSleepingStatus") is True:
        activate_servo("open")

# ================= SLEEP DETECTOR =================
class SleepDetector:
    def __init__(self, resting_hr, sleep_threshold=5, required_minutes=3):
        self.resting_hr = resting_hr
        self.sleep_threshold = sleep_threshold
        self.required_minutes = required_minutes
        self.sleep_counter = 0
        self.is_sleeping = False
        self.lamps_locked = False
        self.servo_activated_today = False

    def time_to_int(self, t):
        return int(t.replace(":", ""))

    def is_between(self, current, start, end):
        c = self.time_to_int(current)
        s = self.time_to_int(start)
        e = self.time_to_int(end)
        return s <= c <= e if s <= e else c >= s or c <= e

    def process_heart_rate(self, hr, current_time):
        # Reset daily servo flag after midnight
        if self.is_between(current_time, "00:00", "03:59"):
            if self.servo_activated_today:
                print("[INFO] New day → resetting curtain flag")
                self.servo_activated_today = False

        # Night lamp auto-off
        if hr < self.resting_hr and self.is_between(current_time, "20:00", "04:00"):
            if not self.lamps_locked:
                turn_off_lamp()
                self.lamps_locked = True

        # Midday lamp unlock
        if self.lamps_locked and self.is_between(current_time, "12:00", "19:59"):
            print("[INFO] Lamps unlocked")
            self.lamps_locked = False

        # Sleep detection
        if hr <= self.resting_hr - self.sleep_threshold:
            self.sleep_counter += 1
            if self.sleep_counter >= self.required_minutes and not self.is_sleeping:
                self.is_sleeping = True
                return "SLEEP_DETECTED"
        else:
            # Wake detection (ONCE PER DAY)
            if (
                self.is_sleeping
                and hr > self.resting_hr
                and self.is_between(current_time, "04:01", "23:59")
                and not self.servo_activated_today
            ):
                self.is_sleeping = False
                self.sleep_counter = 0
                self.servo_activated_today = True
                return "WAKE_DETECTED"

            self.sleep_counter = 0

        return None

# ================= SIMULATION =================
resting_hr = 65
hr_samples = [70,67,66,64,63,62,60,59,60,58,57,62,66,69,72,75,78]
time_samples = [
    "19:50","20:10","20:30","21:00","21:30","22:00","22:30","23:00","23:30",
    "00:30","02:00","06:00","07:30","08:30","09:30","10:30","11:30"
]

detector = SleepDetector(resting_hr)

print("\n--- Starting Simulation ---\n")
GPIO.output(LAMP_PIN, GPIO.HIGH)

for hr, t in zip(hr_samples, time_samples):
    print(f"[Time {t}] HR={hr}")
    status = detector.process_heart_rate(hr, t)

    if status == "SLEEP_DETECTED":
        handle_sleep_event()
    elif status == "WAKE_DETECTED":
        handle_wake_event()

    time.sleep(1)

print("\n--- Simulation Finished ---")
GPIO.cleanup()
