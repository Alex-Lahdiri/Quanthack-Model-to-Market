FROM python:3.10-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r live/requirements.txt
ENV PORT=8080
EXPOSE 8080
# Default: the mission-control web service (serves the dashboard + AI desk over HTTP).
# MetaTrader5 is intentionally NOT installed (Windows-only); the feed + bridge run on the
# Windows box. Northflank cron jobs override CMD with the desk/monitor commands.
CMD ["python", "live/server.py"]
