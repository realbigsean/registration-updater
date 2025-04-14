FROM python:3.10-slim

WORKDIR /app

# Copy the script
COPY ./registration-updater.py /app/registration-updater.py

# Install dependencies
RUN pip install --no-cache-dir requests

# Set default environment variables
ENV SOURCE_RELAY="https://0xafa4c6985aa049fb79dd37010438cfebeb0f2bd42b115b89dd678dab0670c1de38da0c4e9138c9290a398ecd9a0b3110@boost-relay.flashbots.net"
ENV INTERVAL=6

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD ps aux | grep "[r]egistration-updater.py" || exit 1

# Entrypoint that accepts runtime parameters
ENTRYPOINT ["python", "registration-updater.py"]

# Default command if no arguments are provided
CMD ["--target-relay", "${TARGET_RELAY}", "--source-relay", "${SOURCE_RELAY}", "--interval", "${INTERVAL}"]
