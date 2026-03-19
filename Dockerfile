FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY templates ./templates

RUN python -m pip install --no-cache-dir --upgrade \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org \
  pip setuptools wheel

RUN pip install --no-cache-dir \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org \
  fastapi uvicorn jinja2 pyyaml python-multipart

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]