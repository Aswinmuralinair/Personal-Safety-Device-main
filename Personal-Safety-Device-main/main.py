import RPi.GPIO as GPIO
import signal
import time
import json
import os
import threading                                         # ← ADDED
from hardware.comms import SIM7600
from datetime import datetime, timezone, timedelta
from hardware.sensors import SensorManager               # ← ADDED

# --- IMPORTS (for Battery) ---
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Alert, Base
try:
    from hardware.power import INA219Simple, voltage_to_percentage
    I2C_AVAILABLE = True
except ImportError:
    print("WARN: 'smbus2' library not found. Battery monitoring disabled.")
    I2C_AVAILABLE = False
except FileNotFoundError:
    print("WARN: I2C not enabled or hardware not found. Battery monitoring disabled.")
    I2C_AVAILABLE = False
# ----------------------------


def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

def create_dummy_file(path, content="This is a dummy evidence file."):
    dir_name = os.path.dirname(path)
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)
    with open(path, 'w') as f:
        f.write(content)
    print(f"Created dummy file: {os.path.basename(path)}")

def get_db_session():
    engine = create_engine('sqlite:///alerts.db')
    Base.metadata.create_all(engine)
    DBSession = sessionmaker(bind=engine)
    return DBSession()

# ── ADDED: single global SensorManager instance & locks ──────────────────────
sensor_manager = SensorManager()
sensor_manager.start()

_sos_lock = threading.Lock()
_sos_active = False
# ─────────────────────────────────────────────────────────────────────────────


def sos_sequence(trigger_source: str = "button"):
    global _sos_active

    # ── ADDED: guard — only one SOS sequence at a time ───────────────────────
    with _sos_lock:
        if _sos_active:
            print(f"SOS already active, ignoring trigger: {trigger_source}")
            return
        _sos_active = True
    # ─────────────────────────────────────────────────────────────────────────

    print(f"\nSOS ACTIVATED! Source: {trigger_source}")
    config = load_config()
    sim = SIM7600(port=config['serial_port'], baud=config['baud_rate'])
    
    # --- Init Power Monitor ---
    power_monitor = None
    if I2C_AVAILABLE:
        try:
            power_monitor = INA219Simple()
            print("--- Power monitor (INA219) initialized. ---")
        except IOError:
            print("WARN: Could not connect to INA219. Battery monitoring disabled.")
    
    print("--- Connecting to local database... ---")
    session = get_db_session()
    new_alert = Alert(
        device_id=config['device_id'],
        timestamp=datetime.now(timezone.utc)
    )
    # --- NEW: Set default battery status ---
    if not I2C_AVAILABLE:
        new_alert.battery_percentage = "N/A"
    # ---------------------------------------
    session.add(new_alert)
    session.commit()
    print("--- Created new alert row in local database. ---")

    call_placed_status = False
    guardian_sms_status = False
    location_sms_status = False

    print("\n--- Step 1: Placing Emergency Call ---")
    if sim.place_call(config['police_number']):
        time.sleep(15)
        sim.hang_up_call()
        call_placed_status = True
    
    new_alert.call_placed_status = call_placed_status
    
    print("\n--- Step 2: Sending Initial SOS SMS ---")
    guardian_sms_status = sim.send_sms(config['guardian_number'], "SOS! Emergency Alert. Location to follow.")
    
    new_alert.guardian_sms_status = guardian_sms_status
    time.sleep(5)

    print("\n--- Step 3: Sending Location SMS ---")
    location = sim.get_gps_location()
    if location:
        location_sms_status = sim.send_sms(config['guardian_number'], f"Location: {location}")
        new_alert.gps_location = location
    else:
        sim.send_sms(config['guardian_number'], "Location could not be determined.")

    new_alert.location_sms_status = location_sms_status
    
    print("--- Committing initial status to local database... ---")
    session.commit()

    print("\n--- Step 4: Starting 1-Minute Update Loop (GPS + Upload) ---")
    dummy_file_path = os.path.join(config['evidence_dir'], "evidence_sample.txt")
    create_dummy_file(dummy_file_path)
    
    while True:
        print("\n--- [1-Min Cycle] Sending Periodic Update ---")
        
        # --- 1. Battery Check & SMS ---
        if power_monitor:
            try:
                v = power_monitor.get_voltage_V()
                pct = voltage_to_percentage(v)
                battery_pct_str = f"{pct}%"
                print(f"--- [1-Min Cycle] Battery: {v:.2f}V, {battery_pct_str} ---")
                
                # --- NEW: Save battery % to DB object ---
                new_alert.battery_percentage = battery_pct_str
                
                # Send dedicated battery SMS
                sim.send_sms(config['guardian_number'], f"Kavach Battery: {battery_pct_str}")

            except IOError:
                print("Error: Could not read from INA219 during loop.")
                new_alert.battery_percentage = "Error"
            except Exception as e:
                print(f"Error sending battery SMS: {e}")
        # ------------------------------

        # --- 2. GPS Check & SMS ---
        ist_timezone = timezone(timedelta(hours=5, minutes=30), name='IST')
        now_in_ist = datetime.now(ist_timezone)
        sms_timestamp = now_in_ist.strftime("%d-%m-%Y %I:%M:%S %p")

        periodic_location = sim.get_gps_location()
        if periodic_location:
            loc_str = periodic_location
            new_alert.gps_location = periodic_location
            
            try:
                message = f"Location at {sms_timestamp}: {loc_str}"
                sim.send_sms(config['guardian_number'], message)
            except Exception as e:
                print(f"Error sending location update SMS: {e}")
                
        else:
            loc_str = "Not found." # Shorten for SMS
            try:
                message = f"Location at {sms_timestamp}: {loc_str}"
                sim.send_sms(config['guardian_number'], message)
            except Exception as e:
                print(f"Error sending 'no location' SMS: {e}")
        
        # --- NEW: Commit all periodic data (GPS & Battery) ---
        print("--- Committing periodic status to local database... ---")
        session.commit()
        # -----------------------------------------------------
        
        print("\n--- [1-Min Cycle] Checking for Evidence Files ---")
        try:
            files = [f for f in os.listdir(config['evidence_dir']) if os.path.isfile(os.path.join(config['evidence_dir'], f))]
            if not files:
                print("No evidence files found to upload.")
            else:
                print(f"Found {len(files)} file(s). Attempting to upload all...")
                for file_name in files:
                    file_path = os.path.join(config['evidence_dir'], file_name)
                    print(f"Attempting to upload: {file_name}")
                    
                    success, uploaded_filename = sim.upload_alert(
                        config['server_url'], new_alert, file_path
                    )
                    
                    if success:
                        print(f"Successfully uploaded {file_name}.")
                        file_link = config['server_public_url'] + uploaded_filename
                        sim.send_sms(config['guardian_number'], f"New evidence received: {file_link}")
                        
                        current_files = new_alert.uploaded_files or ""
                        new_alert.uploaded_files = current_files + uploaded_filename + ","
                        print("--- Committing uploaded file list to local database... ---")
                        session.commit()
                        
                    else:
                        print(f"Upload failed for {file_name}. Will retry next cycle.")
        
        except Exception as e:
            print(f"An error occurred in the update loop: {e}")

        print("\n--- [1-Min Cycle] Waiting for 60 seconds... ---")
        time.sleep(60)


# ── ADDED: IMU & Heart Rate Threads + Button Callback ─────────────────────────
def _imu_monitor_thread():
    print("--- IMU monitor thread started ---")
    while True:
        try:
            reading = sensor_manager.imu.read()
            if reading.is_fall_detected:
                print(f"[IMU] FALL DETECTED — magnitude={reading.accel_magnitude:.2f} m/s²")
                sos_sequence(trigger_source="fall_detected")
        except Exception as e:
            print(f"[IMU] Read error: {e}")
        time.sleep(0.1)

def _heart_rate_monitor_thread():
    print("--- Heart rate monitor thread started ---")
    while True:
        try:
            reading = sensor_manager.heart_rate.read()
            if reading.is_valid:
                print(f"[HeartRate] BPM={reading.bpm}  SpO2={reading.spo2}%")
            if reading.is_distress_detected:
                print(f"[HeartRate] DISTRESS DETECTED — BPM={reading.bpm}")
                sos_sequence(trigger_source="heartrate_spike")
        except Exception as e:
            print(f"[HeartRate] Read error: {e}")
        time.sleep(5)

def _button_callback(channel):
    """Your existing GPIO callback adapted for the new sos_sequence arguments."""
    sos_sequence(trigger_source="button")
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("--- Checking for database file and tables... ---")
    engine = create_engine('sqlite:///alerts.db')
    Base.metadata.create_all(engine)
    print("--- Database check complete. ---")

    config = load_config()
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(config['sos_button_pin'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    # Updated callback to use _button_callback wrapper instead of direct sos_sequence
    GPIO.add_event_detect(config['sos_button_pin'], GPIO.FALLING, callback=_button_callback, bouncetime=3000)
    
    # ── ADDED: start sensor monitor threads as daemons ────────────────────────
    threading.Thread(target=_imu_monitor_thread, daemon=True).start()
    threading.Thread(target=_heart_rate_monitor_thread, daemon=True).start()
    print("[Sensors] Monitor threads started.")
    print(f"[Sensors] Status: {sensor_manager.status_string()}")
    # ──────────────────────────────────────────────────────────────────────────

    print("SOS device armed. Waiting for trigger (button / fall / heart rate)...")
    
    try:
        signal.pause()
    except KeyboardInterrupt:
        print("\nProgram terminated.")
    finally:
        sensor_manager.stop()    # ← ADDED — clean sensor shutdown
        print("Cleaning up GPIO...")
        GPIO.cleanup()