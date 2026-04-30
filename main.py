import machine
from machine import UART, Pin
import time
time.sleep(3)
from micropyGPS import MicropyGPS   

ADMIN_NUMBER = "+420731101708"
LOCATION_INTERVAL_MS = 60000
GSM_CHECK_INTERVAL_MS = 15000


class GSMManager:
    def __init__(self, uart):
        self.uart = uart
        self.buffer = ""
        self.connected = False

    def _read(self):
        if self.uart.any():
            raw = self.uart.read()
            if raw:
                try:
                    data = raw.decode()
                except:
                    data = ""
                self.buffer += data

                if len(self.buffer) > 1000:
                    self.buffer = self.buffer[-500:]

                print(data)  
                return data
        return ""

    def wait_for(self, keywords, timeout=5000):
        start = time.ticks_ms()
        self.buffer = ""

        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            self._read()

            for k in keywords:
                if k in self.buffer:
                    return self.buffer

            time.sleep_ms(50)

        print("Timeout čekání:", keywords)
        return None

    def send_command(self, cmd, timeout=5000):
        print("CMD:", cmd)
        self.uart.write((cmd + "\r\n").encode())
        return self.wait_for(["OK", "ERROR"], timeout)

    def initialize(self):
        print("Inicializace GSM...")

        for i in range(5):
            if self.send_command("AT"):
                print("GSM OK")
                break
            print("Zkouším znovu...")
            time.sleep(1)
        else:
            print("GSM NEODPOVÍDÁ ")
            return False

        self.send_command("ATE0")
        self.send_command("AT+CMGF=1")
        self.send_command("AT+CNMI=2,1,0,0,0")

        return True

    def check_network(self):
        resp = self.send_command("AT+CREG?", 4000) or ""

        if "+CREG: 0,1" in resp or "+CREG: 0,5" in resp:
            self.send_command("AT+CSQ")      
            self.send_command("AT+CSCA?")
            if not self.connected:
                print("Připojeno k síti ")
            self.connected = True
        else:
            print("Není síť ")
            self.connected = False

        return self.connected

    def send_sms(self, number, message):
        print("Posílám SMS:", message)

        if not self.connected:
            print("Není síť, SMS neodeslána")
            return False

        self.uart.write(f'AT+CMGS="{number}"\r\n'.encode())
        time.sleep_ms(300)

        if not self.wait_for([">"], 5000):
            print("Chybí prompt >")
            return False

        self.uart.write(message.encode() + b"\x1A")

        resp = self.wait_for(["OK", "+CMGS"], 15000)

        if resp:
            print("SMS odeslána ")
            return True
        else:
            print("SMS selhala ")
            return False


class GPSManager:
    def __init__(self, uart):
        self.uart = uart
        self.parser = MicropyGPS(location_formatting='dd')

    def update(self):
        while self.uart.any():
            data = self.uart.read()
            if data:
                for b in data:
                    self.parser.update(chr(b))

    def has_fix(self):
        return (
            self.parser.fix_stat > 0
           
        )

    def get_location(self):
        if not self.has_fix():
            return "GPS bez fixu"

        lat = self.parser.latitude[0] + self.parser.latitude[1] / 60
        lon = self.parser.longitude[0] + self.parser.longitude[1] / 60

        if self.parser.latitude[2] == 'S':
            lat = -lat
        if self.parser.longitude[2] == 'W':
            lon = -lon


        return f"https://maps.google.com/?q={lat},{lon}"


class TrackerApp:
    def __init__(self):
        print("Startuji UART...")

        self.gsm_uart = machine.UART(0, 9600, tx=machine.Pin(0), rx=machine.Pin(1))
        self.gps_uart = machine.UART(1, 9600, tx=machine.Pin(4), rx=machine.Pin(5))

        self.gsm = GSMManager(self.gsm_uart)
        self.gps = GPSManager(self.gps_uart)

        self.last_gsm_check = 0
        self.last_location = 0
        self.first_sms_sent = False

    def run(self):
        print("Čekám na start...")
        time.sleep(5)

        if not self.gsm.initialize():
            print("STOP – GSM nefunguje")
            return

        while True:
            now = time.ticks_ms()

            self.gps.update()

            if time.ticks_diff(now, self.last_gsm_check) > GSM_CHECK_INTERVAL_MS:
                self.gsm.check_network()
                self.last_gsm_check = now

            if self.gsm.connected and not self.first_sms_sent:
                self.gsm.send_sms(ADMIN_NUMBER, "Tracker jede")
                self.first_sms_sent = True

            if (
                self.gsm.connected and
                time.ticks_diff(now, self.last_location) > LOCATION_INTERVAL_MS
            ):
                msg = self.gps.get_location()
                print("Lokace:", msg)

                self.gsm.send_sms(ADMIN_NUMBER, msg)
                self.last_location = now

            time.sleep_ms(200)


print("tracker jede")

app = TrackerApp()
app.run()