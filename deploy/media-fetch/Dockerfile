FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/media-fetch
COPY requirements-media-fetch.txt ./
RUN python -m pip install --no-cache-dir -r requirements-media-fetch.txt \
    && useradd --uid 10001 --create-home validator
COPY app/__init__.py ./app/__init__.py
COPY app/adapters/__init__.py app/adapters/download.py app/adapters/download_network.py app/adapters/download_browser.py app/adapters/douyin_browser.cjs ./app/adapters/
COPY package.json package-lock.json ./
COPY scripts/validate_media_fetch.py scripts/media_fetch_launcher.py ./scripts/
COPY deploy/media-fetch/samples.json ./deploy/media-fetch/samples.json
USER 10001:10001
ENTRYPOINT ["python", "-I", "/opt/media-fetch/scripts/validate_media_fetch.py"]
CMD ["--label", "container", "--output-dir", "/results/phase1c-fetch"]
