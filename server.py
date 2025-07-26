from flask import Flask, request, jsonify
from flask_cors import CORS
from version import __VERSION__
import os
import pexconfig
import printer

app = Flask(__name__)
CORS(app)

ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
TEMP_PATH = os.path.join(ROOT_PATH, "temp")
os.makedirs(TEMP_PATH, exist_ok=True)


@app.after_request
def apply_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


@app.route('/status', methods=['GET'])
def status():
    file_printer = pexconfig.get_file_printer()
    if len(file_printer) == 0 or file_printer == "null":
        file_printer = None

    label_printer = pexconfig.get_label_printer()
    if len(label_printer) == 0 or label_printer == "null":
        label_printer = None

    return jsonify({'status': 'success', 'result': {
        'file': file_printer,
        'label': label_printer,
        'version': __VERSION__,
    }}), 200


@app.route('/print/file', methods=['POST'])
def print_file():
    printer_name = pexconfig.get_file_printer()
    if not printer_name or printer_name == "null":
        return jsonify({'status': 'error', 'message': 'No file printer set'}), 400

    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400

    # Get Data
    file = request.files['file']
    paper = request.form.get('format', 'A6')
    orientation = request.form.get('orientation', 'portrait')
    quantity = int(request.form.get('quantity', 1))

    filename = file.filename or 'label.pdf'
    filename = os.path.basename(filename).replace(' ', '_')
    filepath = os.path.join(TEMP_PATH, filename)

    # Print
    try:
        file.save(filepath)
        printer.file(filepath, paper, orientation, quantity)
        os.remove(filepath)
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500

    return jsonify({'status': 'success', 'result': {
        'filename': filename,
        'printer': printer_name
    }}), 200


@app.route('/print/label', methods=['POST'])
def print_label():
    printer_name = pexconfig.get_label_printer()
    if len(printer_name) == 0 or printer_name == "null":
        return jsonify({'status': 'error', 'message': 'No label printer set'}), 400

    model = request.form.get('model', 'MODEL')
    hashtag = request.form.get('hashtag', '#HASHTAG')
    quantity = int(request.form.get('quantity', 1))

    printer.label(model, hashtag, quantity)
    return jsonify({'status': 'success', 'result': {
        'data': {
            'model': model,
            'hashtag': hashtag,
            'quantity': quantity,
        },
        'printer': printer_name
    }}), 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=4422)
