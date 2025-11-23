FROM python:3.11-slim

WORKDIR /app

# Install Docker CLI and dependencies
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://get.docker.com -o get-docker.sh && \
    sh get-docker.sh && \
    rm get-docker.sh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --upgrade docker requests urllib3

# Copy application
COPY . .

# Expose port
EXPOSE 8080

# Run application
CMD ["python", "app.py"]
