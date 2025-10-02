# Use an official Python image
FROM python:3.10-slim

# Install system dependencies for dlib/face_recognition
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libboost-all-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy your code
COPY . /app

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose port (Railway uses 8080)
EXPOSE 8080

# Start the app
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]