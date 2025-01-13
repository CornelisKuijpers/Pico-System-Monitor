import asyncio
import re
import subprocess

from bleak import BleakClient, BleakScanner
import psutil
import json
import time

# Nordic UART Service UUIDs
UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# Maximum size for BLE packets
MAX_PACKET_SIZE = 20


class PicoMonitorClient:
    def __init__(self):
        self.client = None
        self.connected = False

    async def find_pico(self):
        print("Scanning for Pico-NUS...")
        devices = await BleakScanner.discover()
        for d in devices:
            if d.name and "Pico-NUS" in d.name:
                print(f"Found Pico-NUS at {d.address}")
                return d.address
        return None

    async def connect(self):
        address = await self.find_pico()
        if not address:
            print("No Pico-NUS device found!")
            return False

        print(f"Connecting to {address}...")
        self.client = BleakClient(address)
        try:
            await self.client.connect()
            print("Connected!")
            self.connected = True
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def get_gpu_usage(self):
        try:
            # Try nvidia-smi first
            try:
                output = subprocess.check_output(['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'])
                return float(output.decode('utf-8').strip())
            except:
                pass

            # Try AMD GPU
            try:
                output = subprocess.check_output(['radeontop', '-d-', '-l1'], stderr=subprocess.DEVNULL)
                match = re.search(r'gpu (\d+\.\d+)%', output.decode('utf-8'))
                if match:
                    return float(match.group(1))
            except:
                pass

            # If no GPU found, return 0
            return 0
        except:
            return 0

    def get_system_metrics(self):
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        gpu_percent = self.get_gpu_usage()

        try:
            gpu_temp = 0
            try:
                gpu = psutil.sensors_temperatures().get('amdgpu')
                if gpu:
                    gpu_temp = gpu[0].current
            except:
                pass

            # Compact format to minimize size
            return {
                "c": round(cpu_percent, 1),
                "m": round(memory.percent, 1),
                "g": round(gpu_percent, 1)
            }
        except Exception as e:
            print(f"Error getting metrics: {e}")
            return {"c": 0, "m": 0, "g": 0}

    async def send_metrics(self):
        if not self.connected:
            print("Not connected!")
            return

        try:
            metrics = self.get_system_metrics()
            data = json.dumps(metrics)
            print(f"Sending metrics: {data}")

            # Add packet end marker
            data = data + '\n'

            # Split into chunks if needed
            data_bytes = data.encode()
            for i in range(0, len(data_bytes), MAX_PACKET_SIZE):
                chunk = data_bytes[i:i + MAX_PACKET_SIZE]
                await self.client.write_gatt_char(UART_RX_CHAR_UUID, chunk)
                await asyncio.sleep(0.01)  # Small delay between chunks

        except Exception as e:
            print(f"Error sending metrics: {e}")
            self.connected = False


async def main():
    client = PicoMonitorClient()

    while True:
        try:
            if not client.connected:
                await client.connect()
                if not client.connected:
                    print("Connection failed, retrying in 5 seconds...")
                    await asyncio.sleep(5)
                    continue

            await client.send_metrics()
            await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("\nStopping monitor...")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            client.connected = False
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
