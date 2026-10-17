# tiny-py-fpbroser

A minimal fingerprint browser launcher for Windows x64. It drives an installed
Chrome/Chromium through Playwright and keeps each profile's cookies, storage and
generated fingerprint in a separate directory.

## Features

- Persistent Chrome profiles (`profiles/*.json`, `data/<name>/`)
- Locale, timezone and geolocation derived from the current exit IP (ipinfo.io)
- Per-profile Canvas, WebGL and AudioContext noise
- Speech voices, media devices and installed-font masking for a stock Windows install
- WebRTC policy and optional system proxy handling
- Exit-IP verification through the browser itself

## Requirements

- Windows x64
- Python 3.14+
- Google Chrome or Chromium installed
- `pip install playwright` (no `playwright install` needed)

## Usage

```bat
python fpbrowser.py
```

Select an existing profile or create a new one from the current exit IP.
Press Ctrl+C to close the browser and exit.

## Layout

```
fpbrowser.py      entry point
config.py         paths and fingerprint constants
console.py        console output, key input and termination handling
fingerprint.py    init script, media devices, voices, font hiding
profiles.py       profile creation, upgrade, storage and selection
browser.py        Chrome discovery, network policy, Playwright session
smoke_test.py     platform-independent smoke tests
```

Runtime data is written next to the sources:

```
profiles/<name>.json   reusable browser parameters
data/<name>/           Chrome user-data-dir (cookies, local storage, ...)
```

## Tests

```bat
python smoke_test.py
```

The smoke tests cover platform-independent logic. The Windows console,
registry font enumeration and the real browser session require a Windows x64
run.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
