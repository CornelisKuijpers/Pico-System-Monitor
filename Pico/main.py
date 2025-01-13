import bluetooth
import json
from micropython import const
import time
from machine import Pin, PWM
from ble_advertising import advertising_payload
from Pico_LCD_1_14_V2 import LCD_1inch14

# Nordic UART Service (NUS)
NUS_SERVICE_UUID = bluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')
NUS_RX_CHAR_UUID = bluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E')
NUS_TX_CHAR_UUID = bluetooth.UUID('6E400003-B5A3-F393-E0A9-E50E24DCCA9E')

# BLE flags
_FLAG_READ = const(0x0002)
_FLAG_NOTIFY = const(0x0010)
_FLAG_WRITE = const(0x0008)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)

# IRQ constants
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

class BLEMonitor:
    def __init__(self):
        print("\nInitializing BLE Monitor")
        print("1. Setting up LCD...")
        self.lcd = LCD_1inch14()
        pwm = PWM(Pin(13))
        pwm.freq(1000)
        pwm.duty_u16(65535)  # Full brightness
        
        # Buffer for incoming data
        self.rx_buffer = ""
        
        # Add tracking for min/max values
        self.min_values = {"c": 100, "m": 100, "g": 100}
        self.max_values = {"c": 0, "m": 0, "g": 0}
        self.last_update = 0
        
        # Initialize BLE
        print("2. Setting up BLE...")
        self.ble = bluetooth.BLE()
        print("- Stopping any existing BLE...")
        self.ble.active(False)
        time.sleep_ms(500)
        
        print("- Starting BLE...")
        self.ble.active(True)
        self.ble.config(gap_name='Pico-NUS')
        
        # Register UART Service
        print("3. Registering NUS service...")
        ((self.tx_handle, self.rx_handle),) = self.ble.gatts_register_services((
            (NUS_SERVICE_UUID, (
                (NUS_TX_CHAR_UUID, _FLAG_READ | _FLAG_NOTIFY),
                (NUS_RX_CHAR_UUID, _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE),
            )),
        ))
        
        print(f"- TX handle: {self.tx_handle}")
        print(f"- RX handle: {self.rx_handle}")
        
        # Set handler for IRQ events
        self.ble.irq(self._irq_handler)
        self.connections = set()
        
        # Start advertising
        print("4. Starting advertising...")
        self.advertise()
        
        # Initialize display
        print("5. Setting up display...")
        self.init_display()
        print("Initialization complete!")
    
    def init_display(self):
        # Clear to white
        self.lcd.fill(self.lcd.white)
        
        # Title bar with rounded corners
        self.lcd.fill_rect(0, 0, 240, 25, self.lcd.blue)
        self.lcd.text("System Monitor", 65, 8, self.lcd.white)
        
        # Initialize metrics area
        self.update_metrics({"c": 0, "m": 0, "g": 0})
        self.lcd.show()
    
    def update_min_max(self, metrics):
        for key in metrics:
            if metrics[key] < self.min_values[key]:
                self.min_values[key] = metrics[key]
            if metrics[key] > self.max_values[key]:
                self.max_values[key] = metrics[key]
    
    def draw_bar(self, x, y, value, max_width, color):
        # Background (light version of color)
        self.lcd.rect(x, y, max_width, 10, color)
        # Progress bar
        width = int((value * max_width) / 100)
        if width > 0:
            self.lcd.fill_rect(x, y, width, 10, color)
    
    def update_metrics(self, metrics):
        print("Updating display with metrics:", metrics)
        # Update min/max values
        self.update_min_max(metrics)
        
        # Clear metrics area
        self.lcd.fill_rect(0, 25, 240, 110, self.lcd.white)
        
        # Status line with timestamp
        current_time = time.ticks_ms()
        if self.connections:
            status = "Connected"
            color = self.lcd.green
        else:
            status = "Advertising"
            color = self.lcd.red
        self.lcd.text(f"BLE: {status}", 10, 30, color)
        
        # Metrics display
        y_start = 45
        bar_x = 85
        bar_width = 140
        
        try:
            # CPU
            self.lcd.text("CPU:", 10, y_start, self.lcd.red)
            self.lcd.text(f"{metrics['c']:>4}%", 45, y_start, self.lcd.red)
            self.draw_bar(bar_x, y_start, metrics['c'], bar_width, self.lcd.red)
            self.lcd.text(f"Max:{self.max_values['c']}%", 85, y_start + 12, self.lcd.red)
            
            # Memory
            y_pos = y_start + 25
            self.lcd.text("MEM:", 10, y_pos, self.lcd.green)
            self.lcd.text(f"{metrics['m']:>4}%", 45, y_pos, self.lcd.green)
            self.draw_bar(bar_x, y_pos, metrics['m'], bar_width, self.lcd.green)
            self.lcd.text(f"Max:{self.max_values['m']}%", 85, y_pos + 12, self.lcd.green)
            
            # GPU
            y_pos = y_start + 50
            self.lcd.text("GPU:", 10, y_pos, self.lcd.blue)
            self.lcd.text(f"{metrics['g']:>4}%", 45, y_pos, self.lcd.blue)
            self.draw_bar(bar_x, y_pos, metrics['g'], bar_width, self.lcd.blue)
            self.lcd.text(f"Max:{self.max_values['g']}%", 85, y_pos + 12, self.lcd.blue)
            
            # Show update time
            delta = time.ticks_diff(current_time, self.last_update) if self.last_update else 0
            if delta > 1000:  # If more than 1 second since last update
                self.lcd.text(f"Update: {delta/1000:.1f}s ago", 10, 120, self.lcd.blue)
            
            self.last_update = current_time
            self.lcd.show()
            print("Display updated successfully")
            
        except Exception as e:
            print("Error updating display elements:", e)
    
    def process_metrics(self, data):
        try:
            # Print raw received data
            print("Received raw data:", data)
            
            # Add to buffer
            self.rx_buffer += data.decode()
            print("Current buffer:", self.rx_buffer)
            
            # Check for complete JSON messages
            while '\n' in self.rx_buffer:
                # Split on newline
                line, self.rx_buffer = self.rx_buffer.split('\n', 1)
                print("Processing line:", line)
                
                # Parse and update display
                try:
                    metrics = json.loads(line)
                    print("Parsed metrics:", metrics)
                    self.update_metrics(metrics)
                except json.JSONDecodeError as je:
                    print("JSON parsing error:", je)
                    self.rx_buffer = ""  # Clear buffer on JSON error
                except Exception as e:
                    print("Error updating display:", e)
                    
        except Exception as e:
            print("Error processing data:", e)
            self.rx_buffer = ""  # Clear buffer on error
    
    def _irq_handler(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            print(f"Connected! Handle: {conn_handle}")
            self.connections.add(conn_handle)
            self.update_metrics({"c": 0, "m": 0, "g": 0})
            
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            print(f"Disconnected! Handle: {conn_handle}")
            if conn_handle in self.connections:
                self.connections.remove(conn_handle)
            self.rx_buffer = ""  # Clear buffer
            self.advertise()
            self.update_metrics({"c": 0, "m": 0, "g": 0})
            
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self.rx_handle:
                value = self.ble.gatts_read(value_handle)
                self.process_metrics(value)
    
    def advertise(self):
        name = bytes('Pico-NUS', 'UTF-8')
        adv_data = bytearray([
            0x02, 0x01, 0x06,  # General discoverable
            0x03, 0x03, 0x0A, 0x18,  # Nordic UART Service
            len(name) + 1, 0x09] + list(name))  # Complete name
        
        print("Starting advertising...")
        print(f"Advertisement data: {bytes(adv_data).hex()}")
        self.ble.gap_advertise(100000, adv_data=adv_data)

def main():
    print("=== Starting BLE Monitor ===")
    monitor = BLEMonitor()
    try:
        while True:
            time.sleep_ms(100)
    except Exception as e:
        print(f"Error in main loop: {e}")
        raise

if __name__ == "__main__":
    main()