import os
from datetime import datetime
from flask import Flask, request, jsonify
from pathlib import Path
from waitress import serve
from . import printer
from .. import config
from ..version import __NAME__, __VERSION__
from ..utils import is_int

app = Flask(__name__)

ROOT_PATH = Path(__file__).resolve().parents[3]
TEMP_PATH = ROOT_PATH / "temp"
os.makedirs(TEMP_PATH, exist_ok=True)


@app.after_request
def apply_cors_headers(response):
    origin = config.get_option("server.cors")
    if origin is False or origin is None:
        return response

    if origin is True:
        origin = request.headers.get('Origin')
    if isinstance(origin, str):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


def response_success(data: dict, code: int = 200):
    return jsonify({
        'status': 'success',
        'result': data
    }), code


def response_error(message: str, details: dict | None = None, code: int = 400):
    return jsonify({
        'status': 'error',
        'message': message,
        'details': details or {}
    }), code


@app.route('/pex/status', methods=['GET'])
def _get_status():
    return response_success({
        'name': __NAME__,
        'version': __VERSION__,
        'config': {
            'formats': config.get_option('formats'),
            'printers': config.get_option('printers'),
            'printer_default': config.get_option('printer_default'),
        },
        'printers': printer.list_printers()
    })


@app.route('/pex/printers', methods=['GET'])
def _get_printers():
    printers = printer.list_printers()
    printer_default = config.get_option('printer_default')
    if isinstance(printer_default, str):
        printer_default = printer.resolve_printer_name(printer_default)
    return response_success({
        'printers': printers,
        'printer_default': printer_default,
    })


@app.route('/pex/print', methods=['POST'])
def _post_print():
    args = dict()

    # Default arguments
    args['printer_name'] = request.form.get('printer', config.get_option('printer_default'))
    args['orientation'] = request.form.get('orientation', 'portrait')
    args['quantity'] = int(request.form.get('quantity', 1))

    # Format "paper_format"
    formats = request.form.getlist('format')
    if not formats:
        args['paper_format'] = "A4"
    else:
        if len(formats) == 1 and not is_int(formats[0]):
            args['paper_format'] = formats[0]
        elif len(formats) >= 2 and is_int(formats[0]) and is_int(formats[1]):
            args['paper_format'] = [int(f) for f in formats]
        else:
            args['paper_format'] = formats[0]

    # Print PDF file
    if 'file' in request.files:
        try:
            file = request.files['file']
            timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            filename = os.path.basename(file.filename or f"custom_file-{timestamp}.pdf").replace(' ', '_')
            filepath = os.path.join(TEMP_PATH, filename)
            file.save(filepath)
            args['filepath'] = filepath

            printer.print_file(**args)
            return response_success({
                "message": "The file has been successfully printed.",
                "arguments": args
            })
        except Exception as e:
            return response_error(str(e))

    # Print Label Lines
    elif 'lines' in request.form:
        try:
            args['lines'] = request.form.getlist('lines')
            args['font_name'] = request.form.get('font_name', None),
            args['font_size'] = int(request.form.get('font_size', 10)),
            args['line_height'] = int(request.form.get('line_height', 12)),

            printer.print_lines(**args)
            return response_success({
                "message": "The label has been successfully printed.",
                "arguments": args
            })
        except Exception as e:
            return response_error(str(e))

    # Invalid Command
    else:
        return response_error("You need to either pass a file or the desired lines to print.", request.form)


def run():
    host = config.get_option("server.host") or "0.0.0.0"
    port = int(config.get_option("server.port") or 4422)
    threads = int(config.get_option("server.threads") or 4)
    backlog = int(config.get_option("server.backlog") or 128)
    channel_timeout = int(config.get_option("server.timeout") or 30)

    try:
        serve(
            app,
            host=host,
            port=port,
            threads=threads,
            backlog=backlog,
            channel_timeout=channel_timeout,
            ident=f"PEX/{__VERSION__}"
        )
    except ImportError:
        app.run(debug=True, host=config.get_option("server.host"), port=config.get_option("server.port"))


if __name__ == "__main__":
    run()
