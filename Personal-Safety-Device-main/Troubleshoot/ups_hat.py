from hardware.power import INA219Simple, voltage_to_percentage
import time

try:
    ina = INA219Simple()
    print("UPS HAT detected")

    while True:
        v = ina.get_voltage_V()
        c = ina.get_current_mA()
        p = voltage_to_percentage(v)

        print(f"Voltage: {v:.2f} V")
        print(f"Current: {c:.0f} mA")
        print(f"Battery: {p}%")
        print("-" * 20)
        time.sleep(2)

except Exception as e:
    print("UPS HAT NOT detected:", e)
