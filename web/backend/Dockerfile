# syntax=docker/dockerfile:1
FROM ghcr.io/prefix-dev/pixi:0.80.0 AS build
WORKDIR /app
COPY pixi.toml pixi.lock pyproject.toml README.md LICENSE /app/
COPY geode/ /app/geode/
COPY com/ /app/com/
RUN pixi install --locked -e runtime && pixi shell-hook -e runtime -s bash > /app/runtime-hook.sh

FROM ubuntu:26.04 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.pixi/envs/runtime/bin:$PATH" \
    MPLCONFIGDIR=/app/web/backend/cache/matplotlib
ARG USER_ID_TO_SAVE_FILES=1000
ARG GROUP_ID_TO_SAVE_FILES=1000
# Ubuntu includes an unprivileged user at UID 1000; replace it with the application user.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates supervisor redis-server \
    && rm -rf /var/lib/apt/lists/* \
    && if id ubuntu >/dev/null 2>&1; then userdel -r ubuntu; fi \
    && if getent group ubuntu >/dev/null; then groupdel ubuntu; fi \
    && groupadd -g "${GROUP_ID_TO_SAVE_FILES}" geode \
    && useradd -l -m -u "${USER_ID_TO_SAVE_FILES}" -g geode geode
WORKDIR /app
COPY --from=build /app /app
COPY web/backend/ /app/web/backend/
RUN mkdir -p /app/web/backend/logs /app/web/backend/media /app/web/backend/cache \
    && chown -R geode:geode /app/web/backend/logs /app/web/backend/media /app/web/backend/cache \
    && chmod +x /app/web/backend/entrypoint.sh
USER geode
WORKDIR /app/web/backend
HEALTHCHECK --interval=15s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health-check', timeout=8)" || exit 1
ENTRYPOINT ["/app/web/backend/entrypoint.sh"]
CMD ["supervisord", "-c", "/app/web/backend/supervisord.conf"]
