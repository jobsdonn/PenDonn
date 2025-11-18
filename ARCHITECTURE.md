# PenDonn System Architecture

## Overview

PenDonn is a modular, automated penetration testing system designed to run on Raspberry Pi hardware with dual external WiFi adapters. The system follows a pipeline architecture where each module feeds data to the next.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        PenDonn System                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────┐      ┌──────────────┐     ┌──────────────┐  │
│  │  WiFi Monitor  │ ───> │   Cracker    │ ──> │ Enumerator   │  │
│  │  (wlan1+wlan2) │      │ John/Hashcat │     │    Nmap      │  │
│  └────────────────┘      └──────────────┘     └──────────────┘  │
│         │                        │                     │         │
│         │                        │                     │         │
│         v                        v                     v         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    SQLite Database                        │   │
│  │  - Networks  - Handshakes  - Passwords  - Scans - Vulns  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         │                    │                    │             │
│         v                    v                    v             │
│  ┌────────────┐       ┌────────────┐      ┌────────────┐       │
│  │   Display  │       │  Web API   │      │  Plugins   │       │
│  │ Waveshare  │       │   Flask    │      │   System   │       │
│  └────────────┘       └────────────┘      └────────────┘       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. WiFi Monitor (`core/wifi_monitor.py`)

**Purpose:** Discover WiFi networks and capture WPA/WPA2 handshakes

**Key Functions:**
- Channel hopping across 2.4GHz channels (1-13)
- Beacon frame analysis for network discovery
- EAPOL packet capture for handshakes
- Deauthentication attacks to force handshakes
- Whitelist filtering

**Hardware:**
- Uses two external WiFi adapters
- Adapter 1 (monitor_interface): Passive scanning
- Adapter 2 (attack_interface): Active attacks (deauth)

**Data Flow:**
```
Beacon Frames → Network Discovery → Database
    ↓
EAPOL Packets → Handshake Capture → Cracker Queue
```

### 2. Password Cracker (`core/cracker.py`)

**Purpose:** Crack captured WPA/WPA2 handshakes

**Key Functions:**
- Queue-based handshake processing
- Multi-engine support (John the Ripper, Hashcat)
- Concurrent cracking (configurable workers)
- Automatic format conversion

**Workflow:**
```
Handshake File → Convert to John/Hashcat format
    ↓
Apply wordlist (rockyou.txt)
    ↓
Password found? → Store in database → Trigger enumeration
    ↓
Password not found → Mark as failed
```

**Performance:**
- CPU-based cracking with John the Ripper
- GPU-accelerated cracking with Hashcat (if available)
- Queue prevents overloading

### 3. Network Enumerator (`core/enumerator.py`)

**Purpose:** Scan cracked networks for vulnerabilities

**Key Functions:**
- Automatic network connection
- Host discovery (ping sweep)
- Port scanning (Nmap)
- Service version detection
- Vulnerability checks
- Plugin execution

**Workflow:**
```
Cracked Password → Connect to Network (wlan0)
    ↓
Discover Hosts → Port Scan → Service Detection
    ↓
Built-in Vulnerability Checks
    ↓
Execute Plugins → Store Results
    ↓
Disconnect
```

### 4. Plugin Manager (`core/plugin_manager.py`)

**Purpose:** Load and execute custom vulnerability scanners

**Key Functions:**
- Dynamic plugin discovery
- JSON-based configuration
- Plugin lifecycle management
- Database integration

**Plugin Architecture:**
```
plugins/
├── plugin_name/
│   ├── plugin.json      # Metadata
│   └── scanner.py       # Implementation
```

**Plugin Base Class:**
```python
class PluginBase(ABC):
    @abstractmethod
    def run(self, scan_id, hosts, scan_results):
        """Execute plugin scanning logic"""
        pass
```

### 5. Database (`core/database.py`)

**Purpose:** Centralized data storage

**Schema:**
```sql
Networks
- id, ssid, bssid, channel, encryption, signal_strength
- first_seen, last_seen, is_whitelisted

Handshakes
- id, network_id, bssid, ssid, file_path
- capture_date, status, quality

Cracked_Passwords
- id, handshake_id, ssid, bssid, password
- cracking_engine, crack_time_seconds, cracked_date

Scans
- id, network_id, ssid, scan_type
- start_time, end_time, status, results

Vulnerabilities
- id, scan_id, host, port, service
- vulnerability_type, severity, description
```

### 6. Display (`core/display.py`)

**Purpose:** Real-time status visualization

**Key Functions:**
- Waveshare V4 display driver
- Real-time statistics rendering
- Status indicators
- Progress tracking

**Display Layout:**
```
┌─────────────────────┐
│     PenDonn         │
│  2025-11-18 14:30   │
├─────────────────────┤
│ Networks:        12 │
│ Handshakes:       5 │
│ Passwords:        3 │
│ Scans:            2 │
│ Vulnerabilities: 15 │
├─────────────────────┤
│ ⚡ Cracking: 2      │
└─────────────────────┘
```

### 7. Web Interface (`web/app.py`)

**Purpose:** Browser-based system control

**API Endpoints:**
```
GET  /api/status           - System status
GET  /api/networks         - Discovered networks
GET  /api/handshakes       - Captured handshakes
GET  /api/passwords        - Cracked passwords
GET  /api/scans            - Enumeration scans
GET  /api/vulnerabilities  - Found vulnerabilities
POST /api/export           - Export data
POST /api/database/reset   - Reset database
GET  /api/whitelist        - Get whitelist
POST /api/whitelist        - Add to whitelist
```

**Technology Stack:**
- Flask (web framework)
- Vanilla JavaScript (frontend)
- RESTful API design
- Real-time updates (polling)

## Data Flow

### Complete Attack Chain

```
1. DISCOVERY
   WiFi Monitor → Scan channels → Find networks
        ↓
   Filter whitelist → Store in database

2. CAPTURE
   Network found → Start handshake capture
        ↓
   Send deauth → Capture EAPOL frames
        ↓
   Verify handshake → Store capture file

3. CRACKING
   Handshake captured → Add to queue
        ↓
   Try John the Ripper → Success?
        ↓
   Try Hashcat → Success?
        ↓
   Store password → Trigger enumeration

4. ENUMERATION
   Password cracked → Connect to network
        ↓
   Discover hosts → Port scan
        ↓
   Run vulnerability checks
        ↓
   Execute plugins → Store vulnerabilities

5. REPORTING
   All data in database
        ↓
   Display on screen + Web dashboard
        ↓
   Export to JSON
```

## Concurrency Model

### Threading Strategy

```
Main Process
├── WiFi Monitor Thread
│   ├── Channel Hopper Thread
│   ├── Packet Sniffer Thread
│   └── Capture Monitor Thread
│
├── Cracker Threads (configurable workers)
│   ├── Worker 1
│   └── Worker 2
│
├── Enumerator Thread
│   └── Scan Monitor Thread
│
└── Display Update Thread
```

### Synchronization

- **Database:** Thread-safe SQLite connections
- **Queues:** Used for handshake cracking jobs
- **Locks:** Minimal locking due to SQLite handling
- **Signals:** Clean shutdown via SIGINT/SIGTERM

## Configuration Management

### config.json Structure

```json
{
  "system": {...},      // Global settings
  "wifi": {...},        // WiFi interface config
  "whitelist": {...},   // Protected networks
  "cracking": {...},    // Cracker settings
  "enumeration": {...}, // Scanner settings
  "plugins": {...},     // Plugin config
  "database": {...},    // Database path
  "web": {...},         // Web server settings
  "display": {...}      // Display settings
}
```

## Security Considerations

### Authentication
- Web interface runs on onboard WiFi only (wlan0)
- Secret key for session management
- No authentication by default (local network trusted)

### Privilege Management
- Requires root for:
  - Monitor mode
  - Packet injection
  - Network connection
  - Low-level network operations

### Data Protection
- Database stored locally
- Export includes sensitive data (passwords)
- Backup created on export/reset
- No cloud storage by default

## Extensibility

### Adding New Features

1. **New Vulnerability Scanner**
   - Create plugin in `plugins/`
   - Implement `PluginBase` interface
   - Add `plugin.json`

2. **New Cracking Engine**
   - Modify `core/cracker.py`
   - Add engine-specific logic
   - Update configuration

3. **New Display Type**
   - Modify `core/display.py`
   - Add hardware-specific code
   - Update configuration

## Performance Optimization

### Bottlenecks
1. **Password Cracking** - CPU/GPU intensive
   - Solution: External GPU, cloud cracking
2. **Network Scanning** - Time consuming
   - Solution: Parallel scanning, reduced port range
3. **Database I/O** - Many writes
   - Solution: Batch operations, indexing

### Optimization Strategies
- Channel hopping interval tuning
- Concurrent cracking workers
- Efficient Nmap timing templates
- Database indexing on frequently queried fields

## Monitoring & Logging

### Log Levels
- **DEBUG:** Detailed technical information
- **INFO:** General operational messages
- **WARNING:** Potential issues
- **ERROR:** Errors requiring attention

### Log Files
```
logs/
├── pendonn.log        # Main daemon log
├── pendonn_error.log  # Error output
├── web.log            # Web server log
└── web_error.log      # Web errors
```

### Monitoring
- Systemd journal integration
- Real-time log viewing via journalctl
- Web dashboard statistics
- Display status updates

## Future Architecture Enhancements

### Planned Improvements
1. **Distributed Scanning** - Multiple RPi coordination
2. **Cloud Integration** - Remote dashboard, cloud cracking
3. **Advanced Reporting** - PDF/HTML reports
4. **Real-time Notifications** - Email/Telegram alerts
5. **Machine Learning** - Smart password prediction

---

## Summary

PenDonn is designed as a modular, pipeline-based system where each component handles a specific phase of penetration testing. The architecture emphasizes:

- **Modularity:** Each component is independent
- **Extensibility:** Plugin system for custom scanners
- **Reliability:** Database-backed state management
- **Usability:** Web interface and display output
- **Performance:** Concurrent processing where possible

This design allows for easy maintenance, testing, and enhancement while keeping the system focused on automated, legal penetration testing workflows.
