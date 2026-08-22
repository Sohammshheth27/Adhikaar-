# Adhikaar — DPDP compliance engine + web UI, one container (for Hugging Face Docker Spaces).
FROM python:3.11-slim

# Offline model (baked into the image) + writable cache/browser paths for the HF uid-1000 runtime.
ENV PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HOME=/tmp/hf \
    HOME=/tmp \
    PLAYWRIGHT_BROWSERS_PATH=/tmp/pw

WORKDIR /app
COPY . /app

# Python deps + headless Chromium (with its system libraries).
RUN pip install --no-cache-dir -r backend/requirements.txt \
 && python -m playwright install --with-deps chromium \
 && chmod -R 777 /tmp/pw

# Run the FastAPI app (serves the API AND the frontend/ site) on the HF Spaces port.
WORKDIR /app/backend
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
