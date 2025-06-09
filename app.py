import requests
from io import BytesIO
from flask import Flask, request, jsonify
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.config.parser import ConfigParser
import logging
from datetime import datetime
import threading
import subprocess
import time

app = Flask(__name__)
models_ready = False
converter = None

# Configuring basic logging with timestamp
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Function to monitor NVIDIA GPU usage
def log_gpu_usage():
    while True:
        try:
            # Run nvidia-smi to get GPU usage
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu,utilization.memory', '--format=csv,nounits,noheader'],
                capture_output=True, text=True, check=True
            )
            gpu_usage = result.stdout.strip()
            logger.debug(f"NVIDIA GPU Usage: {gpu_usage} (% utilization.gpu, % utilization.memory)")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to query NVIDIA GPU usage: {str(e)}")
        except Exception as e:
            logger.error(f"Error in GPU monitoring: {str(e)}")
        time.sleep(3)  # Log every 3 seconds

# Start GPU monitoring thread
gpu_thread = threading.Thread(target=log_gpu_usage, daemon=True)
gpu_thread.start()

@app.route('/convert', methods=['GET'])
def convert_pdf_to_markdown():
    logger.debug("Entering /convert endpoint")
    if converter == None:
        logger.error("Converter not loaded")
        return jsonify({'error': 'Converter not loaded'}), 503

    file_id = request.args.get('file_id')
    authorization = request.headers.get('Authorization')
    logger.debug(f"Received file_id: {file_id}")

    if not file_id or not authorization:
        logger.warning("Missing file_id or Authorization header")
        return jsonify({'error': 'Missing file_id or Authorization header'}), 400

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": authorization}
    logger.debug(f"Fetching file from URL: {url}")

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        logger.debug("Successfully fetched file from Google Drive")
        file_stream = BytesIO(response.content)
        logger.debug("PDF conversion started")
        rendered = converter(file_stream)
        logger.debug("PDF conversion completed")
        markdown, _, _ = text_from_rendered(rendered)
        logger.debug("Markdown text extracted")
        return jsonify({'markdown': markdown}), 200
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch file: {str(e)}")
        return jsonify({'error': f"Failed to fetch file: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
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
    logger.info("Starting Flask application")
    app.run(host='0.0.0.0', port=5000)
