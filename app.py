import requests
from io import BytesIO
from flask import Flask, request, jsonify
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.config.parser import ConfigParser
import os

app = Flask(__name__)
models_ready = False
model_dict = None

# Load models only in the first Gunicorn worker
if os.environ.get('GUNICORN_WORKER_ID', '0') == '0':
    try:
        print("Loading models in worker 0...")
        model_dict = create_model_dict()
        print("Models loaded in worker 0")
        models_ready = True
    except Exception as e:
        print(f"Failed to download models at startup: {str(e)}")
        models_ready = False
else:
    # Other workers wait briefly and assume models are ready if worker 0 succeeded
    models_ready = True

config = {
    "disable_image_extraction": True,
    "output_format": "markdown",
    "disable_tqdm": True
}

config_parser = ConfigParser(config)

converter = PdfConverter(
    config=config_parser.generate_config_dict(),
    artifact_dict=model_dict,
    processor_list=config_parser.get_processors(),
    renderer=config_parser.get_renderer()
)

@app.route('/convert', methods=['GET'])
def convert_pdf_to_markdown():
    if not models_ready:
        return jsonify({'error': 'Models not ready'}), 503

    file_id = request.args.get('file_id')
    authorization = request.headers.get('Authorization')

    if not file_id or not authorization:
        return jsonify({'error': 'Missing file_id or Authorization header'}), 400

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": authorization}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        file_stream = BytesIO(response.content)
        rendered = converter(file_stream)
        markdown, _, _ = text_from_rendered(rendered)
        return jsonify({'markdown': markdown}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f"Failed to fetch file: {str(e)}"}), 500
    except Exception as e:
        return jsonify({'error': f"Conversion error: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def healthcheck():
    if not models_ready:
        return jsonify({'status': 'unhealthy', 'error': 'Models not loaded'}), 503
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
