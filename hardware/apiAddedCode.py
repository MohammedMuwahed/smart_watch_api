import os
import time
import json

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

try:
    import requests
except Exception:
    requests = None
    import urllib.request
    import urllib.error


SERVER_BASE = os.environ.get("SMART_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")

LAMP_PIN = 17  
SERVO_PIN = 18  

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(LAMP_PIN, GPIO.OUT)
GPIO.setup(SERVO_PIN, GPIO.OUT)


servo = GPIO.PWM(SERVO_PIN, 50) 
servo.start(0)

def turn_off_lamp():
    GPIO.output(LAMP_PIN, GPIO.LOW)
    print("[HW] Lamp -> OFF")

def turn_on_lamp():
    GPIO.output(LAMP_PIN, GPIO.HIGH)
    print("[HW] Lamp -> ON")

def activate_servo(action="toggle"):
    """
    action: "close" | "open" | "toggle"
    For mock/hardware the same PWM sequence is used; prints clarify intent.
    """
    if action == "close":
        print("[HW] Curtain -> CLOSE (servo action)")
    elif action == "open":
        print("[HW] Curtain -> OPEN (servo action)")
    else:
        print("[HW] Curtain -> TOGGLE (servo action)")

    try:
       
        servo.ChangeDutyCycle(8.5)
        time.sleep(3)
        servo.ChangeDutyCycle(7.5)
        time.sleep(0.2)
    except Exception as e:
        print(f"[WARN] Servo control failed (mock/hw): {e}")

    if action == "close":
        print("[HW] Curtain state: CLOSED\n")
    elif action == "open":
        print("[HW] Curtain state: OPEN\n")
    else:
        print("[HW] Curtain action complete (state depends on mechanical setup)\n")



def _post_update_sleep(is_sleeping: bool):
    url = f"{SERVER_BASE}/update-sleep"
    payload = {"isSleeping": bool(is_sleeping)}
    try:
        if requests:
            r = requests.post(url, json=payload, timeout=5)
            r.raise_for_status()
            return r.json()
        else:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.load(resp)
    except Exception as e:
        print(f"[WARN] Failed POST {url}: {e}")
        return None

def _get_sleep_settings():
    url = f"{SERVER_BASE}/device/settings/sleep"
    try:
        if requests:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            return r.json()
        else:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return json.load(resp)
    except Exception as e:
        print(f"[WARN] Failed GET {url}: {e}")
        return None

def _get_not_sleep_settings():
    url = f"{SERVER_BASE}/device/settings/not-sleep"
    try:
        if requests:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            return r.json()
        else:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return json.load(resp)
    except Exception as e:
        print(f"[WARN] Failed GET {url}: {e}")
        return None

def handle_sleep_event():
    """
    On sleep:
    - POST isSleeping=True
    - read sleep settings; if lights.sleepingStatus==true -> turn off lamp
                           if curtain.sleepingStatus==true -> close curtain
    """
    print("[HW] Sleep detected → notifying server and applying sleep settings.")
    _post_update_sleep(True)
    cfg = _get_sleep_settings()
    if not cfg:
        print("[HW] No sleep settings available; skipping actions.")
        return

    lights_cfg = cfg.get("lights", {})
    curtain_cfg = cfg.get("curtain", {})

    if lights_cfg.get("sleepingStatus") is True:
        turn_off_lamp()
    else:
        print("[HW] Lights: stay as-is on sleep.")

    if curtain_cfg.get("sleepingStatus") is True:
        activate_servo("close")
    else:
        print("[HW] Curtain: stay as-is on sleep.")


def handle_wake_event():
    """
    On wake:
    - POST isSleeping=False
    - read not-sleep settings; if lights.notSleepingStatus==true -> turn on lamp
                                if curtain.notSleepingStatus==true -> open curtain
    """
    print("[HW] Wake detected → notifying server and applying wake settings.")
    _post_update_sleep(False)
    cfg = _get_not_sleep_settings()
    if not cfg:
        print("[HW] No not-sleep settings available; skipping actions.")
        return

    lights_cfg = cfg.get("lights", {})
    curtain_cfg = cfg.get("curtain", {})

    if lights_cfg.get("notSleepingStatus") is True:
        turn_on_lamp()
    else:
        print("[HW] Lights: stay as-is on wake.")

    if curtain_cfg.get("notSleepingStatus") is True:
        activate_servo("open")
    else:
        print("[HW] Curtain: stay as-is on wake.")


resting_hr = 65
hr_samples = [70, 67, 66, 64, 63, 62, 60, 59, 60, 58, 57, 62, 66, 69, 72, 75, 78]
time_samples = [
    "19:50","20:10","20:30","21:00","21:30","22:00","22:30","23:00","23:30",
    "00:30","02:00","06:00","07:30","08:30","09:30","10:30","11:30"
]

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

              
        if hr < self.resting_hr and self.is_between(current_time, "20:00", "04:00"):
            turn_off_lamp()
            self.lamps_locked = True

                  
        if self.lamps_locked and self.is_between(current_time, "12:00", "23:59"):
            print("Unlocking lamps after 12:00 PM")
            self.lamps_locked = False

        if hr <= self.resting_hr - self.sleep_threshold:
            self.sleep_counter += 1
            if self.sleep_counter >= self.required_minutes and not self.is_sleeping:
                self.is_sleeping = True
                return "SLEEP_DETECTED"
        else:
            if self.is_sleeping and hr > self.resting_hr and self.is_between(current_time, "04:01", "23:59"):
                self.is_sleeping = False
                self.sleep_counter = 0
                return "WAKE_DETECTED"

            self.sleep_counter = 0

        return None

detector = SleepDetector(resting_hr)

print("\n Starting Sleep Automation Simulation...\n")

GPIO.output(LAMP_PIN, GPIO.HIGH)
print("Lamp is ON at start.\n")

for minute, (hr, current_time) in enumerate(zip(hr_samples, time_samples), start=1):
    print(f"[Minute {minute}] Time: {current_time} | HR = {hr} bpm")
    status = detector.process_heart_rate(hr, current_time)

    if status == "SLEEP_DETECTED":
        print(" SLEEP DETECTED: applying configured sleep actions.\n")
        handle_sleep_event()

    if status == "WAKE_DETECTED":
        print("WAKE DETECTED: applying configured wake actions.\n")
        handle_wake_event()

    time.sleep(1)

print(" Simulation Finished.")
GPIO.cleanup()
