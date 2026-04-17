FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash svc
USER svc
WORKDIR /home/svc

COPY --chown=svc:svc requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

COPY --chown=svc:svc server.py .

ENV PATH="/home/svc/.local/bin:${PATH}"

EXPOSE 8621

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8621"]
