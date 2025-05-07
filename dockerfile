# Use an official Python runtime as a parent image
FROM --platform=$TARGETPLATFORM python:3.11-slim-bullseye

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    v4l-utils \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /applicacion

# Copy the requirements file into the container
COPY requirements.txt .

# Permitir acceso a dispositivos de video
RUN usermod -a -G video root

ENV CONFIG_PATH=/config/config.yaml


# Copy the rest of the application's files
COPY app/ /app
COPY model/ /model
COPY logs/ /logs  
COPY data/ /data
COPY utils/ /utils
COPY config/ /config

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port streamlit runs in
EXPOSE 8501

# Command to run both start_threads and streamlit 
CMD ["bash", "-c", "python /app/start_threads.py & streamlit run /app/app.py --server.port 8501 --server.address 0.0.0.0"]

