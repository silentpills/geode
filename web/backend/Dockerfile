# syntax=docker/dockerfile:1
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ARG USER_ID_TO_SAVE_FILES=1000
ARG GROUP_ID_TO_SAVE_FILES=1000

# Install system dependencies
# curl + ca-certificates are needed for the uv installer (not in -slim by default)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    supervisor \
    redis-server \
    libpq-dev \
    python3-dev \
    build-essential \
    libffi-dev \
    libssl-dev \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Create user
RUN groupadd -g ${GROUP_ID_TO_SAVE_FILES} dummy-user && \
    useradd -l -u ${USER_ID_TO_SAVE_FILES} -g dummy-user -m dummy-user

# Install uv using the recommended installer and add it to the PATH
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /code
COPY . /code/
RUN mkdir -p /var/log/gunicorn && chmod 755 /var/log/gunicorn

# Now install requirements using uv
RUN uv pip install --system --no-cache-dir -r requirements.txt

COPY ./supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
