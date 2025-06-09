import requests
from io import BytesIO
from flask import Flask, request, jsonify
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.config.parser import ConfigParser

app = Flask(__name__)
models_ready = False
converter = None

@app.route('/convert', methods=['GET'])
def convert_pdf_to_markdown():
    if converter == None:
        return jsonify({'error': 'Converter not loaded'}), 503

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
    if converter == None:
        return jsonify({'status': 'loading'}), 503
    else:
        return jsonify({'status': 'healthy'}), 200

print("Loading converter...")
config = {
    "disable_image_extraction": True,
    "output_format": "markdown",
    "disable_tqdm": True
}
config_parser = ConfigParser(config)
converter = PdfConverter(
    config=config_parser.generate_config_dict(),
    artifact_dict=create_model_dict(),
    processor_list=config_parser.get_processors(),
    renderer=config_parser.get_renderer()
)
print("Converter loaded", flush=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
