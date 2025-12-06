import time
import RPi.GPIO as GPIO

# --- Realtime Database integration (optional) ---
try:
    from firebase_admin import db
    _firebase_available = True
except Exception:
    _firebase_available = False


def _mock_db_get(path):
    # Minimal mock values used for local testing
    if path.endswith('/device/lights') or path.endswith('/device/lights/'):
        return {"sleepingStatus": True, "notSleepingStatus": True, "active": False}
    if path.endswith('/device/curtain') or path.endswith('/device/curtain/'):
        return {"sleepingStatus": True, "notSleepingStatus": True, "active": False}
    if path.endswith('/state/update') or path.endswith('/state/update/'):
        return {"isSleeping": False}
    return {}


def push_state(is_sleeping: bool):
    """Push the sleep state to `/state/update` in Realtime DB (or print when mock)."""
    if _firebase_available:
        try:
            db.reference('/state/update').set({"isSleeping": is_sleeping})
        except Exception as e:
            print(f"[DB ERROR] Failed to push state: {e}")
    else:
        print(f"[MOCK DB] set /state/update -> {{'isSleeping': {is_sleeping}}}")


def get_device_config(device: str):
    """Read `/device/{device}` from Realtime DB, return dict (or mock)."""
    path = f"/device/{device}"
    if _firebase_available:
        try:
            ref = db.reference(path)
            return ref.get() or {}
        except Exception as e:
            print(f"[DB ERROR] Failed to read {path}: {e}")
            return {}
    else:
        return _mock_db_get(path)


def apply_device_actions(is_sleeping: bool):
    """Read device configs and actuate hardware accordingly."""
    lights = get_device_config('lights')
    curtain = get_device_config('curtain')

    if is_sleeping:
        light_action = lights.get('sleepingStatus')
        curtain_action = curtain.get('sleepingStatus')
    else:
        light_action = lights.get('notSleepingStatus')
        curtain_action = curtain.get('notSleepingStatus')

    # Apply light action
    if light_action is True:
        turn_on_lamp()
    else:
        turn_off_lamp()

    # Apply curtain action — on this project we use `activate_servo()` to move the curtain
    # If curtain_action is True we call `activate_servo()`; otherwise we do not move it.
    if curtain_action is True:
        activate_servo()
    else:
        print("Curtain action: no movement (configured to inactive).")


# ---------------- GPIO SETUP ----------------
LAMP_PIN = 17  
SERVO_PIN = 18   # SERVO PIN

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(LAMP_PIN, GPIO.OUT)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# Servo PWM setup
servo = GPIO.PWM(SERVO_PIN, 50)  # 50 Hz PWM
servo.start(0)

# ---------------- ACTION FUNCTIONS ----------------
def turn_off_lamp():
    print("Checking lamp and turning it OFF...")
    GPIO.output(LAMP_PIN, GPIO.LOW)
    print("Lamp is now OFF.\n")

def turn_on_lamp():
    print("Turning lamp ON...")
    GPIO.output(LAMP_PIN, GPIO.HIGH)
    print("Lamp is now ON.\n")

def activate_servo():
    """
    Rotate continuous servo for 1080 degrees (~3 full turns)
    """
    print("Activating servo, rotating blinds 1080 degrees...")

    # continuous rotation forward
    servo.ChangeDutyCycle(8.5)   # Forward rotation (adjust if needed)
    time.sleep(3)                # Spin long enough to complete 3 rotations

    # stop the servo
    servo.ChangeDutyCycle(7.5)   # Stop
    time.sleep(0.5)

    print("Curtains fully opened (1080° rotation).\n")

# ---------------- SAMPLE HEART RATE + TIME DATA ----------------
resting_hr = 65
hr_samples = [70, 67, 66, 64, 63, 62, 60, 59, 60, 58, 57, 62, 66, 69, 72, 75, 78]
time_samples = [
    "19:50","20:10","20:30","21:00","21:30","22:00","22:30","23:00","23:30",
    "00:30","02:00","06:00","07:30","08:30","09:30","10:30","11:30"
]

# ---------------- SLEEP DETECTOR CLASS ----------------
class SleepDetector:
    def __init__(self, resting_hr, sleep_threshold=5, required_minutes=3):
        self.resting_hr = resting_hr
        self.sleep_threshold = sleep_threshold
        self.required_minutes = required_minutes
        self.sleep_counter = 0
        self.is_sleeping = False
        self.lamps_locked = False

    def is_between(self, current, start, end):
        current = int(current.replace(":", ""))
        start = int(start.replace(":", ""))
        end = int(end.replace(":", ""))
        if start <= end:
            return start <= current <= end
        else:
            return current >= start or current <= end

    def process_heart_rate(self, hr, current_time):

        # ----------- NIGHT TIME 20:00 → 04:00 -----------          
        if hr < self.resting_hr and self.is_between(current_time, "20:00", "04:00"):
            turn_off_lamp()
            self.lamps_locked = True

        # ----------- UNLOCK LAMPS AFTER 12:00 PM -----------          
        if self.lamps_locked and self.is_between(current_time, "12:00", "23:59"):
            print("Unlocking lamps after 12:00 PM")
            self.lamps_locked = False

        # ----------- SLEEP DETECTION -----------
        if hr <= self.resting_hr - self.sleep_threshold:
            self.sleep_counter += 1
            if self.sleep_counter >= self.required_minutes and not self.is_sleeping:
                self.is_sleeping = True
                return "SLEEP_DETECTED"
        else:
            # ----------- WAKE DETECTION AFTER 04:00 AM -----------
            if self.is_sleeping and hr > self.resting_hr and self.is_between(current_time, "04:01", "23:59"):
                self.is_sleeping = False
                self.sleep_counter = 0
                return "WAKE_DETECTED"

            self.sleep_counter = 0

        return None

# ---------------- SIMULATION ----------------
detector = SleepDetector(resting_hr)

print("\n Starting Sleep Automation Simulation...\n")

# Lamp ON at start
GPIO.output(LAMP_PIN, GPIO.HIGH)
print("Lamp is ON at start.\n")

for minute, (hr, current_time) in enumerate(zip(hr_samples, time_samples), start=1):
    print(f"[Minute {minute}] Time: {current_time} | HR = {hr} bpm")
    status = detector.process_heart_rate(hr, current_time)

    if status == "SLEEP_DETECTED":
        print(" SLEEP DETECTED: Lamp OFF confirmed.\n")

    if status == "WAKE_DETECTED":
        print("WAKE DETECTED: Opening curtains with servo...\n")
        activate_servo()

        if not detector.lamps_locked:
            turn_on_lamp()

    time.sleep(1)

print(" Simulation Finished.")
GPIO.cleanup()
