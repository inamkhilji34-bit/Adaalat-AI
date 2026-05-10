# Use a lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure data and uploads directories exist
RUN mkdir -p data uploads

# Expose the port Cloud Run uses
EXPOSE 8080

# Command to run the application
# We use uvicorn directly to handle the PORT env var
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
