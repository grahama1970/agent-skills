FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 A_DETECTION_HOME=/state
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home detector \
    && mkdir /state && chown detector:detector /state
USER 10001:10001
EXPOSE 8765
CMD ["a-detection", "serve", "--container-network", "--port", "8765"]
