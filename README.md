# ChetanTheRobot
# AMHR-PD Voice-Controlled Robotic System

## Overview
AMHR-PD is an audio-first robotic control system that connects ESP32 devices to a FastAPI backend. It captures voice input on ESP32-S3 hardware, performs speech-to-text on the backend, routes commands to target devices, and returns speech responses as PCM audio. A web dashboard provides device monitoring and command dispatch.

## Key Features
- Voice command pipeline: wake word → recording → STT → command matching → TTS
- WebSocket device registry and heartbeat monitoring
- REST APIs for device status, command dispatch, and logs
- SQLite persistence for devices, commands, and state snapshots
- Web dashboard for live device monitoring and actions

## Architecture
```
INMP441 Mic  -->  ESP32-S3 (Wake word + Record + Upload)
                         |  HTTP POST /api/audio/upload
                         v
                   FastAPI Backend
        (STT -> Prefix Gate -> Command Match -> TTS)
                         |  WebSocket /ws/{device_id}
                         v
               Target Devices (esp32, esp32s3)
                         |
                         v
                  MAX98357 Amp (Audio Reply)
```

## Repository Structure
```
amhrpd-backend/   FastAPI backend, audio pipeline, database, dashboard
docs/             Documentation and data files
espcod/           ESP32 firmware sketches
```

## Backend Setup
```bash
cd amhrpd-backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Firmware Setup (ESP32-S3 Audio Device)
1. Open espcod/ESPCAM/ESPCAM.ino in Arduino IDE.
2. Set WIFI_SSID, WIFI_PASSWORD, BACKEND_HOST.
3. Select ESP32-S3 board and correct COM port.
4. Upload firmware and open Serial Monitor at 115200 baud.

## Dashboard
Open:
```
http://<BACKEND_HOST>:8000/
```

## API Highlights
- WebSocket: /ws/{device_id}
- Audio upload: POST /api/audio/upload?device_id=<id>
- Devices: GET /api/devices
- Command dispatch: POST /api/command
- Logs: GET /api/command-logs, GET /api/system/logs

## Testing
- Audio pipeline scripts: docs/AUDIOTESTCOD
- Health check: GET /health
- Dashboard updates every 5 seconds

## Troubleshooting
- Device not connecting: verify Wi-Fi, backend IP, and port 8000
- No audio response: confirm WebSocket active and speaker wiring
- STT failures: check Python dependencies and CPU usage
