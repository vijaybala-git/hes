FROM python:3.12-slim

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# PORT defaults to 8080 (Fly.io); HF overrides to 7860 via its own env
ENV PORT=8080

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source, data, and assets
COPY --chown=user src/  ./src/
COPY --chown=user data/ ./data/
COPY --chown=user docs/assets/ ./docs/assets/

EXPOSE $PORT
CMD ["sh", "-c", "solara run src/app.py --host 0.0.0.0 --port $PORT"]
