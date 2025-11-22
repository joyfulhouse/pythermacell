# pythermacell Examples

This directory contains example scripts demonstrating various features of the pythermacell library.

## Prerequisites

Before running these examples:

1. **Install pythermacell**:
   ```bash
   pip install pythermacell
   ```

2. **Set up credentials**:
   - Replace `"your@email.com"` and `"your_password"` in each example with your Thermacell account credentials
   - Alternatively, use environment variables (see below)

3. **Ensure you have devices**:
   - You must have Thermacell LIV devices registered to your account
   - Devices must be online and connected to Wi-Fi

## Examples

### 1. Basic Control (`basic_control.py`)

**What it demonstrates:**
- Authentication with Thermacell API
- Device discovery
- Turning devices on/off
- Setting LED colors
- Refreshing device state

**Run:**
```bash
python examples/basic_control.py
```

**Output:**
```
Connecting to Thermacell API...

Discovering devices...
Found 1 device(s)

Device: Living Room
  Model: Thermacell LIV Hub
  Firmware: 5.3.2
  Serial: ABC123456
  Online: True
  Powered: False

Turning device ON...
  ✓ Device turned on successfully

Setting LED to GREEN...
  ✓ LED color set successfully

Current Device State:
  Power: ON
  LED Power: ON
  LED Brightness: 80%
  LED Hue: 120° (Green ≈ 120°)
  LED Saturation: 100%
  Refill Life: 75.5%
  Runtime: 120 minutes
```

---

### 2. Monitor Devices (`monitor_devices.py`)

**What it demonstrates:**
- Monitoring multiple devices
- Concurrent status checks
- Continuous monitoring loop
- Alert detection (low refill, errors, offline)
- Formatted status display

**Run:**
```bash
python examples/monitor_devices.py
```

**Output:**
```
Monitoring 2 device(s)...
Press Ctrl+C to stop

======================================================================
Thermacell Device Monitor - 2025-01-15 14:30:00
======================================================================

Device 1: Living Room
  Model:      Thermacell LIV Hub
  Status:     Online
  Power:      ON
  State:      Protected
  Refill:     75.5%
  Runtime:    120 min

Device 2: Bedroom
  Model:      Thermacell LIV Hub
  Status:     Online
  Power:      OFF
  State:      Off
  Refill:     15.2%
  Runtime:    0 min
  ⚠️  ALERTS:  LOW REFILL (15.2%)

Updating in 30 seconds... (Press Ctrl+C to stop)
```

**Features:**
- Updates every 30 seconds
- Shows refill warnings when < 20%
- Detects offline devices
- Displays error codes
- Press Ctrl+C to stop

---

### 3. Resilient Client (`resilient_client.py`)

**What it demonstrates:**
- Circuit breaker pattern
- Exponential backoff retries
- Rate limiting support
- Comprehensive error handling
- Resilience pattern configuration

**Run:**
```bash
python examples/resilient_client.py
```

**Output:**
```
Configuring resilience patterns...

Circuit Breaker: threshold=3, recovery=30.0s
Exponential Backoff: base=1.0s, max=30.0s, retries=5
Rate Limiter: default_delay=60.0s, max=300.0s

Connecting to Thermacell API...
Circuit State: closed

✓ Successfully retrieved 1 device(s)
Circuit State: closed
Failure Count: 0

Devices:
  1. Living Room (Thermacell LIV Hub)
     Online: True
     Powered: True
     Refill: 75.5%

==================================================
Circuit Breaker Status:
  State: closed
  Failures: 0/3
  Successes: 0

✓ Circuit is CLOSED - normal operation

==================================================
Final Circuit Breaker State:
  State: closed
  Total Failures: 0
```

**Benefits:**
- Automatic retry on temporary failures
- Prevents cascading failures with circuit breaker
- Respects API rate limits
- Detailed error messages

---

## Using Environment Variables

To avoid hardcoding credentials in the examples, you can use environment variables:

**Create a `.env` file:**
```env
THERMACELL_USERNAME=your@email.com
THERMACELL_PASSWORD=your_password
```

**Modify examples to use environment variables:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

username = os.getenv("THERMACELL_USERNAME")
password = os.getenv("THERMACELL_PASSWORD")

if not username or not password:
    print("Error: Set THERMACELL_USERNAME and THERMACELL_PASSWORD environment variables")
    exit(1)
```

**Install python-dotenv:**
```bash
pip install python-dotenv
```

---

## Common Issues

### Authentication Fails

**Problem:** `AuthenticationError: Authentication failed`

**Solutions:**
- Verify your username and password are correct
- Check that your account is active
- Try logging in to the Thermacell mobile app first

### No Devices Found

**Problem:** `No devices found`

**Solutions:**
- Ensure devices are registered to your account
- Check devices are online in the Thermacell app
- Verify devices are connected to Wi-Fi
- Wait a few minutes after device setup

### Connection Errors

**Problem:** `ThermacellConnectionError: Connection error`

**Solutions:**
- Check your internet connection
- Verify API endpoint is accessible
- Try again in a few minutes (temporary outage)
- Check firewall/proxy settings

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'pythermacell'`

**Solutions:**
- Install the package: `pip install pythermacell`
- If installed from source: `pip install -e .`
- Verify virtual environment is activated

---

## Advanced Usage

### Session Injection

For applications that manage their own aiohttp sessions (like Home Assistant):

```python
from aiohttp import ClientSession
from pythermacell import ThermacellClient

async with ClientSession() as session:
    client = ThermacellClient(
        username=username,
        password=password,
        session=session  # Use your session
    )

    async with client:
        devices = await client.get_devices()
        # Session is NOT closed when client exits
```

### Custom Resilience Configuration

Fine-tune resilience patterns for your use case:

```python
from pythermacell.resilience import CircuitBreaker, ExponentialBackoff

# Aggressive retry for critical operations
aggressive_backoff = ExponentialBackoff(
    base_delay=0.5,      # Start quickly
    max_delay=10.0,      # Don't wait too long
    max_retries=10,      # Many attempts
    jitter=True
)

# Conservative circuit breaker
conservative_breaker = CircuitBreaker(
    failure_threshold=10,  # Allow more failures
    recovery_timeout=120,  # Longer recovery time
    success_threshold=3    # Need more successes
)
```

### LED Color Presets

Common LED colors using HSV:

```python
# RGB-like colors
RED = (0, 100, 100)
GREEN = (120, 100, 100)
BLUE = (240, 100, 100)
YELLOW = (60, 100, 100)
CYAN = (180, 100, 100)
MAGENTA = (300, 100, 100)
WHITE = (0, 0, 100)  # Low saturation = white

# Usage
await device.set_led_color(*GREEN)
```

---

## More Information

- **Full Documentation**: See [README.md](../README.md)
- **API Reference**: See [docs/API.md](../docs/API.md)
- **Source Code**: See [src/pythermacell/](../src/pythermacell/)
- **Tests**: See [tests/](../tests/)

---

## Contributing

Have a useful example? We'd love to include it!

1. Create your example script
2. Add documentation to this README
3. Test it thoroughly
4. Submit a pull request

**Guidelines:**
- Include clear comments
- Handle errors gracefully
- Use meaningful variable names
- Add output examples
- Keep it simple and focused

---

**Happy coding with pythermacell! 🐛🔧**
