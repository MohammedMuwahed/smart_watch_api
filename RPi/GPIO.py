# Minimal mock of RPi.GPIO for development/testing on non-RPi platforms

BCM = "BCM"
BOARD = "BOARD"
OUT = "OUT"
IN = "IN"
LOW = 0
HIGH = 1
PUD_UP = "PUD_UP"
PUD_DOWN = "PUD_DOWN"

_pin_state = {}

def setmode(mode):
    print(f"[MOCK GPIO] setmode({mode})")

def setwarnings(flag):
    # no-op for mock
    pass

def setup(pin, mode, pull_up_down=None):
    _pin_state[pin] = LOW
    print(f"[MOCK GPIO] setup pin {pin} as {mode} pull={pull_up_down}")

def output(pin, value):
    _pin_state[pin] = value
    print(f"[MOCK GPIO] pin {pin} -> {value}")

def input(pin):
    val = _pin_state.get(pin, LOW)
    print(f"[MOCK GPIO] read pin {pin} -> {val}")
    return val

def cleanup():
    print("[MOCK GPIO] cleanup()")
    _pin_state.clear()


class PWM:
    def __init__(self, pin, freq):
        self.pin = pin
        self.freq = freq
        self.running = False
        self.duty = 0
        print(f"[MOCK GPIO] PWM created on pin {pin} at {freq}Hz")

    def start(self, duty_cycle):
        self.running = True
        self.duty = duty_cycle
        print(f"[MOCK GPIO] PWM start {duty_cycle}% on pin {self.pin}")

    def ChangeDutyCycle(self, duty_cycle):
        self.duty = duty_cycle
        print(f"[MOCK GPIO] PWM duty cycle -> {duty_cycle}% on pin {self.pin}")

    def stop(self):
        self.running = False
        print(f"[MOCK GPIO] PWM stopped on pin {self.pin}")