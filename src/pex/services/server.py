import os
from datetime import datetime
from flask import Flask, request, jsonify
from . import printer
from .. import config
from ..version import __NAME__, __VERSION__

app = Flask(__name__)

ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
TEMP_PATH = os.path.join(ROOT_PATH, "temp")
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
            'printers': config.get_option('printers')
        },
        'printers': printer.list_printers()
    })


@app.route('/pex/printers', methods=['GET'])
def _get_printers():
    printers = printer.list_printers()
    return response_success(printers)


@app.route('/pex/print', methods=['POST'])
def _post_print():
    printer_name = request.form.get('printer', config.get_option('printer_default'))
    paper_format = request.form.get('format')
    orientation = request.form.get('orientation', 'portrait')
    quantity = int(request.form.get('quantity', 1))

    if 'file' in request.files:
        file = request.files['file']
        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        filename = os.path.basename(file.filename or f"custom_file-{timestamp}.pdf").replace(' ', '_')
        filepath = os.path.join(TEMP_PATH, filename)
        file.save(filepath)

        try:
            args = (
                filepath,
                printer_name,
                paper_format,
                orientation,
                quantity,
            )
            printer.print_file(*args)
            return response_success({
                "message": "The file has been successfully printed.",
                "arguments": args
            })
        except Exception as e:
            return response_error(str(e))
    elif 'lines' in request.form:
        raw = request.form.get('lines', '')
        lines = raw.splitlines() if isinstance(raw, str) else list(raw)
        try:
            args = (
                lines,
                printer_name,
                paper_format,
                orientation,
                quantity,
                request.form.get('font_name', None),
                int(request.form.get('font_size', 10)),
                int(request.form.get('line_height', 12)),
            )
            printer.print_lines(*args)
            return response_success({
                "message": "The label has been successfully printed.",
                "arguments": args
            })
        except Exception as e:
            return response_error(str(e))
    else:
        return response_error("You need to either pass a file or the desired lines to print.", request.form)


if __name__ == "__main__":
    app.run(debug=True, host=config.get_option("server.host"), port=config.get_option("server.port"))
