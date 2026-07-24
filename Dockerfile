# Single image, two roles (see docker-compose.yml's `command:` overrides):
# the gateway (`app.main:app`) and the mock upstream
# (`src.mock_upstream.main:app`). One image, not two Dockerfiles --
# both roles share the exact same dependency set and source tree, and
# nothing about which role a container plays is baked in at build time.
#
# Runtime dependencies only (requirements.txt) -- this image is for
# running the demo, not for testing, linting, or type-checking it.
# requirements-dev.txt/requirements-benchmark.txt are deliberately never
# installed here.
FROM python:3.11-slim

WORKDIR /app

# Leverages Docker's layer cache: dependencies (large, slow to install --
# torch + gliner in particular) only reinstall when requirements.txt
# itself changes, not on every source-code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY src/ src/

# No CMD/ENTRYPOINT here -- docker-compose.yml's `command:` sets the
# actual role (gateway vs. mock upstream) per service, from this one
# built image.
