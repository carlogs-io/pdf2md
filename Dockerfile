# Use NVIDIA's CUDA base image for better GPU support
FROM nvidia/cuda:12.4.0-base-ubuntu24.04

# Set the working directory in the container
WORKDIR /app

# Install system dependencies and Python
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Create and activate a virtual environment
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Copy the Python script and requirements into the container
COPY requirements.txt .

# Install Python dependencies in the virtual environment
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app.py .

# Expose the port the app runs on
EXPOSE 5000

# Command to run the app with Gunicorn for production
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
