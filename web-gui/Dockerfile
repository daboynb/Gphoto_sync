FROM python:3.11-slim

WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --upgrade docker requests urllib3

# Copy application
COPY . .

# Expose port
EXPOSE 8080

# Run application
CMD ["python", "app.py"]
