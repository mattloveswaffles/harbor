# Harbor backend: one container, one worker (the demo clock and scheduler live in the process).
# Build and run from backend/:
#   docker build -t harbor-backend .
#   docker run -p 8000:8000 --env-file .env harbor-backend
FROM python:3.13-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 HARBOR_MODE=demo

# Dependencies first, so code changes don't reinstall them
COPY pyproject.toml ./
RUN mkdir harbor && touch harbor/__init__.py && pip install --no-cache-dir -e . && rm -rf harbor

# The code and the recorded demo data (Milton replay, sensors, prices, evacuation data)
COPY harbor ./harbor
COPY data ./data
COPY tools ./tools

EXPOSE 8000
CMD ["sh", "-c", "uvicorn harbor.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
