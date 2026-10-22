PEX - Changelog
===============

## Version 0.5.0 (Beta)
- Add: About dialog with copyright, bundled-tool licenses and project links.
- Fix: Move first-open PDF imports off the UI thread; show saved aliases while discovering printers.
- Update: Shared desktop field styling and shorter Settings menu labels.
- Add: API token management in the desktop UI: masked display, copy, generation and saving.
- Fix: Single-instance configuration dialogs and asynchronous printer discovery with loading feedback.
- Info: API authentication is enabled by default. Configure a token and allowed web origin before using browser clients.
- Add: Authenticated API, explicit origin allowlist, bounded input validation and consistent JSON errors.
- Add: Per-printer FIFO queues, durable job IDs/status, optional asynchronous responses and idempotency keys.
- Add: Bounded process calls and conservative unknown states; no automatic retry after uncertain submission.
- Add: Runtime dependency metadata, pinned runtime versions and regression tests.
- Update: Separate spooler restart from explicitly confirmed queue deletion.
- Update: Isolated update preflight, pinned candidate commits, recovery snapshots and restart attempts on failure.
- Fix: Missing / Wrong tcl/tk paths (at least on Windows machines).
- Fix: Duplicate Linux submissions, concurrent PDF filename collisions, per-job paper/orientation/copies.
- Fix: Windows printing no longer changes shared printer defaults; custom labels require an existing driver form.
- Fix: Atomic cross-process configuration updates, preserved legacy configuration and packaged defaults.
- Fix: Headless CLI, Linux service return types and checked Windows service installation steps.
- Fix: Main-thread UI updates, stable default-printer selection and automatic Windows administrator elevation.
- Fix: Label font measurement, orientation, wrapping, overflow and explicit Windows-1252 text support.

## Version 0.4.1 (Beta)
- Add: Support per-line font-declaration for print_label.
- Add: New FPDF2 dependency, which replaces reportlab, for better font-support.
- Add: New common updater script for UI + CLI.
- Update: Install new requirements / reinstall pex package on updater.
- Update: Clean up server.py arguments dictionary.
- Fix: Using `add_cascade` instead of `add_command` (which still worked on windows though).
- Fix: `_set_icon` did not set the desired icon correctly.

## Version 0.4.0 (Beta)
- Info: New project / folder structure including `pyproject.toml`.
- Add: New `get_option`, `set_option`, `delete_option` functions instead of per-config ones.
- Add: New CLI interface for interacting with PEX.
- Add: New `utils.py` runtime utility functions.
- Add: New experimental method to check when a printer job is done, to prevent spooler / queue errors.
- Add: Using threading to improve UI performance.
- Add: Waitress instead of FLASK internal development server.
- Update: Renamed HTTP server routes, using `/pex` as prefix.
- Update: More-common / general-use `print_file` / `print_label` function structures.
- Update: Fix pathing due to new folder structure.
- Update: Clean up all project files and source code.
- Update: Allow declaring as many printers as desired + one default printer.
- Update: Minor changes on the tk desktop UI.
- Update: Service handling on windows & linux.
- Fix: Experimental fix for spooler / printer queue failures (stuck documents, mostly on windows systems).
- Remove: flask-cors / pdfplumber dependencies.

## Version 0.3.1 (Beta)
- Add: New option to change linux printing utility command.
- Fix: Linux printing utility command.

## Version 0.3.0 (Alpha)
- Add: Linux compatibility using PM2.

## Version 0.2.1 (Alpha)
- Fix: Correctly respond on label printer path.
- Fix: Version number on GUI.

## Version 0.2.0 (Alpha)
- Add: Support for format, orientation, and quantity in server.py.
- Add: New update command to the interface (runs git pull and restarts service).
- Add: Display / Respond Version number via server.py and the interface.
- Update: Changed form data field name from pdf to file.
- Update: Include the printer name in server responses.

## Version 0.1.0 (Alpha)
- Initial Release