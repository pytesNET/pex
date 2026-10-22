<p align="center">
  <a href="https://github.com/pytesNET/pex"><img src="github-icon.png" alt="PEX logo" width="128" height="128"></a>
</p>

# PEX — Printer Execution Service

**P**rinter **ex**ecution service and server utility.

PEX is a lightweight Python-based printer service and server. It sends PDF files
and text labels directly to local printers without opening the usual print dialog.
This is especially useful for web apps, PWAs, kiosk systems and warehouse
workstations where labels need to be printed quickly.

The service is accessible through simple HTTP requests. Configure printers and
manage the service using the CLI or the provided Tk desktop application.

You can use the [pex-client](https://github.com/pytesNET/pex-client) TypeScript
library to interact with PEX from JavaScript. Your client must support the API's
bearer token and job responses.

## Dependencies

**Required for Linux**

- Python 3.10+.
- CUPS client commands (`lp`, `lpstat`) and a configured printer.
- Tkinter (usually `python3-tk`), only for the desktop application.
- Node.js and PM2, only for managed background service support.

**Required for Windows**

- Python 3.10+ and pywin32 (installed with the Python dependencies).
- Tkinter, only for the desktop application.
- NSSM 2.24 x64, included as `tools/nssm.exe`, for service management: [Website](https://nssm.cc/).
- SumatraPDF 3.5.2 x64, included as `tools/sumatra_pdf.exe`, for PDF printing: [Website](https://sumatrapdfreader.org).

## Installation

1. Clone the repository and enter the project directory:

   ```sh
   git clone https://github.com/pytesNET/pex.git
   cd pex
   ```

2. Create a virtual environment. On Linux, use `python3` if necessary:

   ```sh
   python -m venv .venv
   ```

3. Activate the environment using the command for your shell:

   ```sh
   source .venv/bin/activate
   ```

   ```bat
   .venv\Scripts\activate.bat
   ```

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

4. Install the Python dependencies:

   ```sh
   python -m pip install -r requirements.txt
   ```

   Use `requirements.lock` instead for the pinned, tested dependency versions.


5. Install PEX as an editable package:

   ```sh
   python -m pip install -e .
   pex --version
   ```

Close PEX windows before manually reinstalling on Windows so Pip can replace the
console launcher.

## Configuration

Use **Printers** in `pex ui` to select your printers, or configure an alias and
default through the CLI:

```sh
pex config printers.labels "Exact OS printer name"
pex config printer_default labels
pex config server.cors https://warehouse.example
```

Replace the printer name and application origin with your values. Common options:

| Option | Default | Description |
| --- | --- | --- |
| `printers` | `{}` | Printer aliases mapped to OS printer names |
| `printer_default` | `null` | Default printer alias/name; configure before printing without an explicit printer |
| `formats` | ISO A sizes and `label` (51 × 25 mm) | Paper dimensions in millimetres |
| `server.host` / `server.port` | `127.0.0.1` / `4422` | HTTP listen address |
| `server.cors` | `false` | Allowed browser origin, or an array of origins |
| `server.require_auth` | `true` | Require bearer-token authentication |
| `server.token` | Generated on first server start | API token; `PEX_API_TOKEN` overrides it |
| `server.max_copies` / `server.max_jobs` | `100` / `100` | Copy limit and maximum queued/active jobs |
| `server.max_upload_mb` | `10` | Request-body limit, including multipart overhead |
| `server.process_timeout` | `30` seconds | Per-process print timeout |
| `server.job_retention_hours` | `24` | Job history and duplicate-request retention |

Read, copy, generate or save the token in **Settings > Manage API Token** in `pex ui`.
The token is masked until you choose Show. An environment token is displayed
read-only when `PEX_API_TOKEN` is set for the UI process.

Alternatively, start `pex run` once to generate the token, then read it from
another activated terminal with `pex config server.token`. Browser origins must match exactly,
without a path or trailing slash. With `server.cors=false`, browser requests with
an Origin header are rejected. Native clients still require the token.

Local overrides are stored in `config.json`; built-in defaults live only in
`src/pex/defaults.json`. Job metadata is stored in `jobs.sqlite3`, while PDFs are
temporary files. Set `PEX_DATA_DIR` if the CLI and service should share a different
data directory. Use a repository checkout for the complete management application.

## Usage

Run `pex help` to list commands, or `pex --version` to show the installed version.

**Desktop application:** `pex ui` opens the management window and automatically
requests administrator privileges on Windows. Allow the Windows elevation prompt
to continue. It does not start the HTTP server by itself. Linux does not request
Windows-style elevation.

**About:** the About menu shows the application version, copyright, bundled-tool
licenses and a link to the GitHub repository.

**Foreground server:** `pex run` starts the HTTP service. Keep the terminal open;
stop it with Ctrl+C. The default address is `http://127.0.0.1:4422` on the machine
running PEX.

**Background service:** install and start the managed service with:

```sh
pex install
pex start
pex status
```

Use `pex stop`, `pex restart` and `pex uninstall` to manage it. Windows uses NSSM
and may require an elevated terminal. Linux uses PM2; configure PM2 startup
separately if it should return after a reboot.

**Settings:** `pex config server.port` reads a value; `pex config server.port 4422`
sets it. `pex config --delete custom.option` removes an override.

**Updates:** `pex update` checks and tests an upstream update before deployment.
It requires a clean Git checkout and network access. Recovery snapshots are kept
in `recovery/`; recovery after a partial failure is manual.

On Windows, **Restart Spooler** keeps pending documents. The separate **Clear pending Jobs** action deletes all queued Windows jobs, including those from
other applications, and requires confirmation.

## HTTP API

Send `Authorization: Bearer YOUR_TOKEN` with API requests. The default base URL is
`http://127.0.0.1:4422`; in a browser this refers to the browser workstation.
For LAN access, configure the host and protect the connection appropriately.

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/pex/status` | Service version, printer configuration and available printers |
| GET | `/pex/printers` | OS printer names, configured aliases and the resolved default printer |
| POST | `/pex/print` | Submit a PDF or text label |
| GET | `/pex/jobs/<id>` | Read a job's state and result |

The printer-list response includes `result.aliases`, a mapping of configured aliases
to OS printer names, such as `{"labels": "Zebra ZD411"}`. Use an alias as the display
label in your interface and as the `printer` value when printing. Configured aliases
remain listed even when their printers are currently unavailable; `result.printers`
contains the OS-discovered names.

### Print requests

Send multipart form data with exactly one PDF upload or text lines. Text-only
requests also accept URL-encoded form data; JSON request bodies are not supported.

| Field | Description / default |
| --- | --- |
| `file` | One PDF upload; mutually exclusive with `lines` |
| `lines` | Repeated text/JSON-object fields, or a JSON array in one form field |
| `printer` | Case-sensitive alias or OS printer name; defaults to `printer_default` |
| `paper_format` | Configured name, JSON pair such as `[51,25]`, or two repeated dimension fields; default `A4` |
| `format` | Legacy alias for `paper_format`; conflicting values are rejected |
| `orientation` | `portrait` / `P` or `landscape` / `L`; default `portrait` |
| `quantity` | Copies, from 1 to the configured limit; default 1 |
| `font_name` | Text only: `helvetica`, `times` or `courier`; default `helvetica` |
| `font_size` | Text only: 1–144 points; default 10 |
| `line_height` | Text only: 1–300 points, at least the font size; default 12 |

Line objects support `text`, `font`, `size`, `height` and boolean `bold`, `italic`,
`underline`, `strikethrough` fields. Generated text must fit on one label and use
Windows-1252 characters; upload a PDF with embedded fonts for other Unicode text.
Windows requires a matching paper size in the printer driver. Portrait uses the
shorter page dimension as width; use landscape for a wide label.

Example text label (requires the configured `labels` printer alias):

```sh
curl --header "Authorization: Bearer YOUR_TOKEN" --header "Idempotency-Key: order-123-label-1" --data-urlencode "lines=Item 123" --data-urlencode "lines=Shelf A1" --data-urlencode "printer=labels" --data-urlencode "paper_format=label" --data-urlencode "orientation=landscape" http://127.0.0.1:4422/pex/print
```

For PDFs, replace the text fields with multipart fields such as
`--form "file=@label.pdf" --form "printer=labels" --form "paper_format=label"`.
In PowerShell, use `curl.exe` if `curl` resolves to an alias.

### Responses and job status

Successful responses contain `status: "success"` and a `result` object. Print
results include `message`, normalized `arguments`, `job` and `replayed`.
The `Location` header points to `/pex/jobs/<id>` for polling with the same token.

| Job state | Meaning |
| --- | --- |
| `queued` | Waiting for its printer |
| `processing` | Submission is in progress |
| `submitted` | Accepted by the print backend; physical output is not confirmed |
| `failed` | Setup or validation prevented submission |
| `unknown` | Outcome is uncertain, or the service restarted with unfinished work |

HTTP 200 from a print request confirms submission; HTTP 202 means the job is still
pending. Add `Prefer: respond-async` to skip waiting. Otherwise PEX waits up to
`server.timeout` (default 30 seconds). Each printer processes its queue in order.

Use a unique `Idempotency-Key` for each intended print operation and reuse it when
retrying the same request. Identical requests return the original job; different
content with the same key returns HTTP 409. Keys are retained with job history
(default 24 hours). PEX never automatically retries uncertain submissions or
replays unfinished jobs after a restart. Check the printer before reprinting.

Errors contain `status`, `message`, `code` and `details`:

```json
{
  "status": "error",
  "message": "Authentication is required.",
  "code": "unauthorized",
  "details": {}
}
```

| HTTP status | Meaning |
| --- | --- |
| 400 | Invalid print parameters or content |
| 401 / 403 | Missing/incorrect token or denied browser origin |
| 404 | Endpoint or job not found |
| 409 | Idempotency-key conflict |
| 413 | Upload or form-data limit exceeded |
| 500 | Unexpected server error |
| 502 | Print submission failed or is uncertain; inspect `details.job` |
| 503 | Authentication not configured or queue/history unavailable/full |

## Testing

Check dependencies and run the local regression suite:

```sh
python -m pip check
python -m unittest discover -s tests -v
```

Tests simulate printer and service operations without submitting real print jobs.
Before deployment, also verify actual label size, copies, margins, offline-printer
behavior and browser access on the intended Windows or Linux workstation.

## Licenses & Copyright

Published under the MIT License \
Copyright © 2024 - 2026 pytesNET <sam@pytes.net>

This project uses and includes

- `nssm` for non-sucking service management on windows, which is licensed under [Public Domain](https://git.nssm.cc/nssm/nssm/src/master/README.txt)
- `SumatraPDF` for PDF printing on windows, which is licensed under [GNU GPLv3](https://github.com/sumatrapdfreader/sumatrapdf/blob/master/COPYING) (and includes components under BSD-style licenses).
