from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import pexconfig
import printer

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'temp'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


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
    }}), 200


@app.route('/print/file', methods=['POST'])
def print_file():
    printer_name = pexconfig.get_file_printer()
    if not printer_name or printer_name == "null":
        return jsonify({'status': 'error', 'message': 'No file printer set'}), 400

    if 'pdf' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400

    pdf_file = request.files['pdf']
    filename = pdf_file.filename or 'label.pdf'
    filename = os.path.basename(filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    try:
        pdf_file.save(filepath)
        printer.file(filepath)
        os.remove(filepath)
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500

    return jsonify({'status': 'success', 'result': {'message': 'Success', 'filename': filename}}), 200


@app.route('/print/label', methods=['POST'])
def print_label():
    printer_name = pexconfig.get_label_printer()
    if len(printer_name) == 0 or printer_name == "null":
        return jsonify({'status': 'error', 'message': 'No label printer set'}), 400

    data = request.get_json()
    if not data or 'model' not in data or 'hashtag' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    printer.label(data['model'], data['hashtag'], data['quantity'] if 'quantity' in data else 1)
    return jsonify({'status': 'success', 'result': {'message': 'Success'}}), 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=4422)
