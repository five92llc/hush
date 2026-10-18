FROM python:3.12-slim

# WHISPER=1 bakes in audio scanning (bigger image). WHISPER=0 = subtitles only.
ARG WHISPER=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-whisper.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$WHISPER" = "1" ]; then pip install --no-cache-dir -r requirements-whisper.txt; fi

COPY hush ./hush

RUN useradd --system --uid 1000 --create-home hush && mkdir -p /data /config && chown hush /data
USER hush

ENV HUSH_CONFIG=/config/config.yaml HUSH_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8642
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8642/api/session')"
CMD ["python", "-m", "hush"]
