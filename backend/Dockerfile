# EcoReport AI backend — production image
# Essentials are installed strictly; fonts and optional tools are installed
# best-effort so a package missing from a given base image can never fail the
# whole deploy (the app degrades gracefully: charts fall back to DejaVu Sans,
# PDFs fall back to plain conversion).
FROM python:3.11-slim

# python3-uno lands in the system dist-packages, outside this slim image's
# default import path, so make it reachable from the app.
ENV PYTHONPATH=/usr/lib/python3/dist-packages \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    DEBIAN_FRONTEND=noninteractive

# --- essential: DOCX -> PDF conversion + PDF page rendering ---------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        python3-uno \
        fontconfig \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && PYTHONPATH=/usr/lib/python3/dist-packages python3 -c \
       "import uno; print('UNO bridge available')" 

# --- best effort: Arabic + chart fonts, LibreOffice automation bridge -----
RUN apt-get update; \
    for pkg in fonts-hosny-amiri fonts-noto-core fonts-ibm-plex \
               fonts-dejavu-core; do \
        apt-get install -y --no-install-recommends "$pkg" \
            || echo "WARNING: optional package $pkg unavailable, continuing"; \
    done; \
    fc-cache -f >/dev/null 2>&1 || true; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Generated reports and uploaded attachments live here. Attach a persistent
# disk at /data (or enable S3 storage) to keep them across redeploys.
ENV REPORT_DIR=/data/reports \
    MEDIA_DIR=/data/attachments
RUN mkdir -p /data/reports /data/attachments

EXPOSE 8000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]
