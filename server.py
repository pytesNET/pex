from flask import Flask, request, jsonify
from flask_cors import CORS
import base64
import os
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
    return jsonify({'status': 'success', 'result': {}}), 200


@app.route('/print/file', methods=['POST'])
def print_file():
    data = request.get_json()

    if not data or 'filename' not in data or 'filedata' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    filename = os.path.basename(data['filename'])
    filedata = data['filedata']
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try:
        with open(filepath, "wb") as file:
            file.write(base64.b64decode(filedata))
        printer.file(filepath)
        os.remove(filepath)
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500

    return jsonify({'status': 'success', 'result': {'message': 'Success', 'filename': filename}}), 200


@app.route('/print/label', methods=['POST'])
def print_label():
    data = request.get_json()

    if not data or 'model' not in data or 'hashtag' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    printer.label(data['model'], data['hashtag'], data['quantity'] if 'quantity' in data else 1)
    return jsonify({'status': 'success', 'result': {'message': 'Success'}}), 200


@app.route('/print/tag', methods=['POST'])
def print_tag():
    data = request.get_json()

    if not data or 'model' not in data or 'hashtag' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    print_label(data['model'], data['hashtag'], data['quantity'] if 'quantity' in data else 1)
    return jsonify({'status': 'success', 'result': {'message': 'Success'}}), 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=4422)
