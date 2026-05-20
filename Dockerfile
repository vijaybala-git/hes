FROM python:3.12-slim

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source, data, and assets
COPY --chown=user src/  ./src/
COPY --chown=user data/ ./data/
COPY --chown=user docs/assets/ ./docs/assets/

EXPOSE 7860
CMD ["solara", "run", "src/app.py", "--host", "0.0.0.0", "--port", "7860"]
