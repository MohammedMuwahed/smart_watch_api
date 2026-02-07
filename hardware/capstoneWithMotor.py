import time
import RPi.GPIO as GPIO

LAMP_PIN = 17  
SERVO_PIN = 18   

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(LAMP_PIN, GPIO.OUT)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# Servo 
servo = GPIO.PWM(SERVO_PIN, 50)  
servo.start(7.5)

# Action is here -->
def turn_off_lamp():
    print("Checking lamp and turning it OFF...")
    GPIO.output(LAMP_PIN, GPIO.LOW)
    print("Lamp is now OFF.\n")

def turn_on_lamp():
    print("Turning lamp ON...")
    GPIO.output(LAMP_PIN, GPIO.HIGH)
    print("Lamp is now ON.\n")

def activate_servo():
    def activate_servo():
    
        print(" Activating MG995, simulating 360° rotation to open curtains...\n")

        sero.ChangeDutyCycle(8.5)
        time.sleep(0.6)
        sero.ChangeDutyCycle(0)

    print(" Curtains opened (360° simulation), servo STOPPED.\n")


#  SAMPLE HEART RATE + TIME DATA "our mock data "
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
