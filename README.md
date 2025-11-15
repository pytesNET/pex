PEX - Printer Execution Service
===============================
**P**rinter **ex**ecution service and server utility.

PEX is a lightweight Python-based printer service and server. It allows direct print jobs to local 
printers without triggering the usual print dialog. This is especially useful for web apps, PWAs, or 
kiosk systems where seamless printing is mandatory.

The printer service is accessible via simple HTTP requests, you can configure your printer service 
using the CLI interface or the provided tk application. 

## Dependencies
**Required for Linux**
- node.js + pm2

**Required for Windows**
- nssm (2.24 x64, included in `/tools`), [Website](https://nssm.cc/)
- SumatraPDF (3.5.2 x64, included in `/tools`), [Website](https://sumatrapdfreader.org)

## Installation

1. Clone this repository
```sh
git clone https://www.github.com/pytesNET/pex
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

4. Install dependencies
```sh
pip install -r requirements.txt
```

5. Install PEX as a python package
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

Start the server (without service)
```sh
pex run
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

This service provides a few simple HTTP endpoints to interact with system printers for printing files and text labels.

All responses follow this basic JSON structure:

```
{
    "status": "success",
    "result": { ... }               // response content
}
```

or in case of errors:

```
{
    "status": "error",
    "message": "<error_message>"
    "details": { ... }              // optional debug details
}
```

### `GET localhost:4422/pex/status`

Returns general information about the PEX service, its version, and current configuration.

**Example Response**

```
{
    "status": "success",
    "result": {
        "name": "PEX - Printer Execution Service",
        "version": "<pex_version>",
        "config": {
            "formats": {
                "A6": [105, 148]
            },
            "printer_default": "files",
            "printers": {
                "labels": "Brother QL-800",
                "files": "Canon TS8300 series"
            }
        },
        "printers": []
    }
}
```

### `GET localhost:4422/pex/printers`

Lists all printers currently available on the host operating system.

**Example Response**

```
{
    "status": "success",
    "result": {
        "printer_default": "<printer_or_null>",
        "printers": [
            "Adobe PDF",
            "Canon TS8300 series",
            "Microsoft Print to PDF",
        ],
    }
}
```

### `POST localhost:442/pex/print`

Prints either a file or a list of text lines. This endpoint expects a `multipart/form-data` request.

**Request**

Either `file` or `lines` must be provided — not both.

| Field          | Type            | Description                                                             |
| -------------- | --------------- | ----------------------------------------------------------------------- |
| `file`         | File            | The file to print (can be omitted if `lines` is used).                  |
| `lines`        | Array<string>   | Lines of text to print (ignored if `file` is used).                     |
| `printer`      | string          | The printer alias or system name. Defaults to `"default"`.              |
| `paper_format` | string or array | The paper format (e.g., `"A4"`, `"A6"`, or `[210, 297]`).               |
| `orientation`  | string          | `"portrait"` / `"P"` or `"landscape"` / `"L"`. Default: `"portrait"`.   |
| `quantity`     | integer         | Number of copies to print. Default: `1`.                                |
| `font_name`    | string          | Font name (only used when printing text lines). Default: `"Helvetica"`. |
| `font_size`    | number          | Font size in pixels (used for labels only). Default: `10`.              |
| `line_height`  | number          | Line height in points (used for labels only). Default: `12`.            |

**Example Response**

```
{
    "status": "success",
    "result": {
        "message": "<success_message>",
        "arguments": { <arguments_used_to_print> }
    }
}
```

### Notes
- The PEX service abstracts the OS printing system (`lp` on Linux, `SumatraPDF` / Win32 APIs on Windows).
- All printer names are case-sensitive as reported by the host system.
- Temporary print files are automatically deleted after the job completes.
- On Windows, SumatraPDF must be installed or available in `tools/sumatra_pdf.exe`.

## License
Published under the MIT License \
Copyright © 2024 - 2026 pytesNET <sam@pytes.net>

This project uses and includes
- `nssm` for non-sucking service management on windows, which is licensed under [Public Domain](https://git.nssm.cc/nssm/nssm/src/master/README.txt)
- `SumatraPDF` for PDF printing on windows, which is licensed under [GNU GPLv3](https://github.com/sumatrapdfreader/sumatrapdf/blob/master/COPYING) (and includes components under BSD-style licenses).