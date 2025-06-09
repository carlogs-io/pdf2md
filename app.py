import requests
import tempfile
import os
from flask import Flask, request, jsonify
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.config.parser import ConfigParser
import logging
import threading
import subprocess
import time
import torch

app = Flask(__name__)
converter = None

# Logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s +0000] [%(process)d] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def log_gpu_usage():
    while True:
        try:
            result = subprocess.run(
                ['nvidia-smi'],
                capture_output=True, text=True, check=True
            )
            logger.debug(result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to query NVIDIA GPU usage: {str(e)}")
        except Exception as e:
            logger.error(f"Error in GPU monitoring: {str(e)}")
        time.sleep(3)

def setup_gpu_monitoring():
    gpu_thread = threading.Thread(target=log_gpu_usage, daemon=True)
    gpu_thread.start()

def log_device_info():
    cuda_available = torch.cuda.is_available()
    device = torch.device("cuda" if cuda_available else "cpu")
    logger.debug(f"CUDA Available: {cuda_available}")
    logger.debug(f"Current Device: {device}")
    if cuda_available:
        logger.debug(f"GPU Device Name: {torch.cuda.get_device_name(0)}")
        logger.debug(f"Current GPU Index: {torch.cuda.current_device()}")
        logger.debug(f"Total GPUs Available: {torch.cuda.device_count()}")

def check_converter_ready():
    if converter is None:
        logger.error("Converter not loaded")
        return jsonify({'error': 'Converter not loaded'}), 503
    return None

def init_converter():
    global converter
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

def convert_to_markdown(file_content, source="unknown"):
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
            logger.debug(f"Temporary file {temp_file_path} created")
        logger.debug(f"PDF conversion started for {source}")
        rendered = converter(temp_file_path)
        logger.debug(f"PDF conversion completed for {source}")
        markdown, _, _ = text_from_rendered(rendered)
        logger.debug("Markdown text extracted")
        return jsonify({'markdown': markdown}), 200
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        return jsonify({'error': f"Conversion error: {str(e)}"}), 500
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.debug(f"Temporary file {temp_file_path} deleted")
            except Exception as e:
                logger.error(f"Failed to delete temporary file {temp_file_path}: {str(e)}")

def handle_conversion_request(file_content, source):
    if error_response := check_converter_ready():
        return error_response
    if not file_content:
        logger.warning("No file data provided")
        return jsonify({'error': 'No file data provided'}), 400
    return convert_to_markdown(file_content, source)

setup_gpu_monitoring()
log_device_info()

@app.route('/convert-gdrive', methods=['GET'])
def convert_pdf_from_gdrive():
    logger.debug("Entering /convert-gdrive endpoint")
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
        return handle_conversion_request(response.content, "Google Drive")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch file: {str(e)}")
        return jsonify({'error': f"Failed to fetch file: {str(e)}"}), 500

@app.route('/convert', methods=['POST'])
def convert_pdf_to_markdown():
    logger.debug("Entering /convert endpoint")
    return handle_conversion_request(request.data, "direct upload")

@app.route('/health', methods=['GET'])
def healthcheck():
    if converter is None:
        logger.warning("Converter not loaded, status: loading")
        return jsonify({'status': 'loading'}), 503
    return jsonify({'status': 'healthy'}), 200

init_converter()

if __name__ == '__main__':
    logger.info("Starting Flask application")
    app.run(host='0.0.0.0', port=5000)
