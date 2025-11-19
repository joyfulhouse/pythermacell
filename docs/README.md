# pythermacell Documentation

Complete documentation for the pythermacell library - a Python client for Thermacell IoT devices.

## Quick Navigation

### 📖 User Documentation
- [Main README](../README.md) - Project overview and quick start
- [CHANGELOG](CHANGELOG.md) - Version history and changes
- [Examples](../examples/README.md) - Code examples and usage patterns

### 🏗️ Architecture
- [Architecture Overview](architecture/README.md) - System design and components
- [Authentication](architecture/AUTHENTICATION.md) - JWT authentication flow
- [Resilience Patterns](architecture/RESILIENCE.md) - Circuit breaker, retry logic, rate limiting

### 🔌 API Reference
- [API Overview](api/README.md) - ESP RainMaker API endpoints
- [Discovered Endpoints](api/DISCOVERED_ENDPOINTS.md) - Complete endpoint catalog from Android APK analysis
- [LED Control](api/LED_CONTROL.md) - ⚠️ **LED color control - Saturation parameter causes crashes**
- [Groups API](api/GROUPS_API.md) - Device grouping functionality
- [OTA Updates](api/OTA_UPDATE_ENDPOINTS.md) - Over-the-air firmware updates

### 🧪 Testing
- [Testing Guide](testing/TESTING.md) - Unit and integration test documentation
- [Integration Test Results](testing/INTEGRATION_TEST_RESULTS.md) - Live API test results
- [Integration Test README](../tests/integration/README.md) - Running integration tests

### 🔬 Research & Analysis
- [API Gap Analysis](research/API_GAP_ANALYSIS.md) - Complete ESP RainMaker API coverage analysis
- [Focused Gap Analysis](research/API_GAP_ANALYSIS_FOCUSED.md) - Device control priority features
- [Code Review Feedback](research/CODE_REVIEW_FEEDBACK.md) - Development review notes
- [Device Power Fix](research/DEVICE_POWER_FIX.md) - Power control parameter debugging
- [Improvements](research/IMPROVEMENTS.md) - Future enhancement proposals

## Documentation Organization

### Directory Structure

```
docs/
├── README.md                    # This file - documentation index
├── CHANGELOG.md                 # Version history
│
├── api/                         # API endpoint documentation
│   ├── README.md                # API overview
│   ├── DISCOVERED_ENDPOINTS.md  # Complete endpoint catalog (54 endpoints)
│   ├── LED_CONTROL.md           # ⚠️ LED control (critical: saturation crashes)
│   ├── GROUPS_API.md            # Group management
│   └── OTA_UPDATE_ENDPOINTS.md  # OTA firmware updates
│
├── architecture/                # System architecture docs
│   ├── README.md                # Architecture overview
│   ├── AUTHENTICATION.md        # Auth flow and JWT handling
│   └── RESILIENCE.md            # Resilience patterns
│
├── testing/                     # Test documentation
│   ├── TESTING.md               # Testing guide
│   └── INTEGRATION_TEST_RESULTS.md  # Live API test results
│
└── research/                    # Research and development analysis
    ├── API_GAP_ANALYSIS.md              # Full API coverage analysis
    ├── API_GAP_ANALYSIS_FOCUSED.md      # Priority features for device control
    ├── CODE_REVIEW_FEEDBACK.md          # Development review notes
    ├── DEVICE_POWER_FIX.md              # Power control debugging
    └── IMPROVEMENTS.md                  # Enhancement proposals
```

### Root-Level Files
Only these markdown files should be in the project root:
- `README.md` - Main project README
- `CLAUDE.md` - Claude Code instructions
- `LICENSE` - Project license

All other documentation belongs in `docs/`.

### Writing Documentation

When creating new documentation:

1. **Choose the right category**:
   - `api/` - API endpoint details, parameter specs, request/response formats
   - `architecture/` - System design, component interaction, design patterns
   - `testing/` - Test guides, results, coverage reports
   - `research/` - Analysis, investigations, APK findings, debugging notes

2. **Use descriptive names**:
   - Good: `LED_CONTROL.md`, `AUTHENTICATION.md`
   - Bad: `notes.md`, `stuff.md`

3. **Include metadata** at the top:
   ```markdown
   # Document Title

   **Category**: API Reference | Architecture | Testing | Research
   **Last Updated**: YYYY-MM-DD
   **Related**: Links to related docs
   ```

4. **Cross-reference** related docs:
   - Use relative paths: `[Authentication](../architecture/AUTHENTICATION.md)`
   - Update index files when adding new docs

## Contributing to Documentation

When adding new documentation:

1. Create file in appropriate subdirectory
2. Update this README.md with a link
3. Update category README if applicable
4. Include cross-references to related docs
5. Follow the metadata format above

## External References

**Note**: The `research/` directory contains reference materials and is excluded from git:
- Home Assistant Reference Implementation
- Android APK Analysis
- ESP RainMaker API Documentation

See `.gitignore` for excluded research materials.
