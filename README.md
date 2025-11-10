PEX - Printer Execution Service
===============================
**P**rinter **ex**ecution service and server utility.

With PEX, print jobs can be sent directly to the printer without going through the standard print dialog. This is 
especially useful for web projects, Progressive Web Applications (PWAs), or similar tools that aim to bypass some 
print previews to provide a more native and seamless user experience.

The printer service is accessible via simple HTTP requests, you can configure your printer service using the CLI 
interface or the provided tk application.

## Dependencies
**Required for Linux**
- node.js + pm2

**Required for Windows**
- nssm (2.24 x64, included in `/tools`)
- SumatraPDF (3.5.2 x64, included in `/tools`)

## Installation

1. Clone this repository
```sh
git clone https://www.github.com/pytesNET/pex pex
```

2. Create a virtual environment
```sh
python -m venv .venv
```

3. Activate your virtual environment
```sh
source .venv\bin\activate     # on Linux
.venv\Scripts\activate        # on Windows
```

4. Install PEX as a python package
```sh
pip install -e .
```

## Usage

Show help
```sh
pex help
```

Start the GUI
```sh
pex ui
```

Run CLI commands
```sh
pex install
pex start
pex status
pex stop
pex uninstall
pex update
pex config
```

## Printing

### `GET localhost:4422/pex/status`

### `GET localhost:4422/pex/printers`

### `POST localhost:4422/pex/print`