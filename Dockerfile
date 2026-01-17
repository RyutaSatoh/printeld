FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if needed (e.g. libmagic)
# RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set python path
ENV PYTHONPATH=/app

CMD ["python", "print_etl_d/main.py"]
