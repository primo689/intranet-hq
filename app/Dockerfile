FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data TZ=America/Chicago
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && useradd -u 1000 -m hq && mkdir -p /data && chown 1000:1000 /data
COPY . .
EXPOSE 8080
# one worker on purpose: the daily-brief scheduler lives in this process
ENTRYPOINT ["python", "/app/entrypoint.py"]
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8080", "--timeout", "90", "server:app"]
