FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir .
USER 1000
# the API needs a database and the round in hand; the image's default shows the agent on the simulated market
CMD ["dma", "demo", "--rounds", "2"]
