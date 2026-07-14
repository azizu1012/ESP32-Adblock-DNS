# REST API Documentation

The ESP32 runs an embedded HTTP server (using `esp_http_server.h`) on Port 80. All endpoints exchange JSON payloads.

---

## Anti-DDoS Rate Limiting
All API endpoints are protected by a native Rate Limiter. If requests exceed **15 requests per second** from any source, the server will immediately return `400 Too Many Requests` or drop the connection to protect LwIP sockets from TCP PCB exhaustion.

---

## Endpoints

### 1. `GET /api/stats`
Fetches real-time system metrics and DNS statistics.

**Response**:
```json
{
  "queries": 1250,
  "blocked": 340,
  "uptime": 3600,
  "top": [
    {"d": "ads.google.com", "c": 45, "g": ["ads"]},
    {"d": "telemetry.microsoft.com", "c": 12, "g": ["telemetry"]}
  ],
  "recent": [
    ["example.com", false, ["ok"], 2, "safelist", "192.168.1.5"]
  ],
  "sys": {
    "ram_free": 210,
    "ram_total": 320,
    "flash_free": 300,
    "flash_total": 1500,
    "cpu_temp": 45.5,
    "cpu_freq": 240,
    "ip": "192.168.1.100",
    "dns": "1.1.1.1"
  }
}
```

### 2. `POST /api/upload`
Uploads a new `blocked.bin` Bloom Filter to the SPIFFS partition. This uses HTTP chunked transfer to stream the file directly into flash memory without RAM buffering.

### 3. `GET /api/safelist`
Returns the array of custom safelisted domains.

**Response**:
```json
["my-smart-tv.com", "api.github.com"]
```

### 4. `POST /api/safelist/add`
Adds a domain to the custom safelist.

**Payload**:
```json
{"domain": "new-domain.com"}
```

### 5. `POST /api/safelist/remove`
Removes a domain from the custom safelist.

**Payload**:
```json
{"domain": "new-domain.com"}
```

### 6. `POST /api/config/wifi`
Updates WiFi credentials and upstream DNS in `config.json`. Automatically triggers a reboot.

**Payload**:
```json
{
  "ssid": "MyWiFi",
  "password": "SecretPassword",
  "dns": "8.8.8.8"
}
```

### 7. `POST /api/config/dhcp`
Clears static IP configurations from `config.json` and reboots the ESP32 to revert to DHCP mode.

### 8. `POST /api/reboot`
Triggers a soft reboot of the ESP32.
