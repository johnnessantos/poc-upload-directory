FROM python:3.11.6-slim as builder
WORKDIR /app
ADD . /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

ENV PYTHONPATH="${PYTHONPATH}:$PWD"
ENV PYTHONPATH="${PYTHONPATH}:$PWD"

RUN python -m venv venv && \
    python -m pip install --no-cache-dir -r requirements.txt

CMD ["hypercorn", "main:app",  "-b=0.0.0.0:80"]