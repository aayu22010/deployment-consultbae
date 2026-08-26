# Use an official lightweight Python image
FROM python:3.13.7-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Install system dependencies
# (Added 'ffmpeg' since this is an audio app, which is commonly required for audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project source code
COPY . .

# Expose the port Flask runs on (default is 5000, change to 8000 if your app.py specifies it)
EXPOSE 5000

# Run the pipeline sequentially: merge -> check -> tag -> start Flask app
CMD sh -c "python merge_sources.py && \
           python check_db.py && \
           python app.py"
