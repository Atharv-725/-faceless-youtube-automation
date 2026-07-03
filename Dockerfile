FROM n8nio/n8n:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg && rm -rf /var/lib/apt/lists/*

RUN pip install --break-system-packages edge-tts

USER node
