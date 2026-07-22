# EcoReport AI backend — production image
# Includes LibreOffice + Arabic fonts so PDF output works out of the box.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg

# System packages: LibreOffice (DOCX -> PDF) + Amiri / Noto fonts (Arabic)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-hosny-amiri \
        fonts-noto-core \
        python3-uno \
        fonts-ibm-plex \
        poppler-utils \
        fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Report files are written here; attach a persistent disk to /data on your
# host if you want local files to survive redeploys (or use S3 storage).
ENV REPORT_DIR=/data/reports
RUN mkdir -p /data/reports

EXPOSE 8000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]
