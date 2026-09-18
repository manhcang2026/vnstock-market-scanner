FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# SSI distributes the legacy FCData Python client as a local archive.
# The archive is intentionally not committed to the public repo.
COPY vendor/ /tmp/ssi_vendor/
RUN set -eux; \
    pkg="$(find /tmp/ssi_vendor -maxdepth 1 -type f \( -name 'ssi_fc_data*.tar.gz' -o -name 'ssi_fc_data*.whl' \) | head -n 1)"; \
    test -n "$pkg"; \
    pip install --no-cache-dir "$pkg"; \
    rm -rf /tmp/ssi_vendor

# VPS SSI SDK hardening:
# - do not print HTTP headers/credentials
# - require SSL certificate verification
RUN sed -i 's/print(self.headers)/# print(self.headers)/' \
      /usr/local/lib/python3.11/site-packages/ssi_fc_data/signalr/transports/_transport.py \
    && sed -i 's/verify_ssl=False/verify_ssl=True/' \
      /usr/local/lib/python3.11/site-packages/ssi_fc_data/signalr/transports/_transport.py

COPY app/ ./app/
RUN mkdir -p /app/data

CMD ["python", "-m", "app.main"]
