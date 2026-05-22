FROM python:3.12-slim

# tini fixes Solara's signal handling in Docker — without it Solara can hang on startup
RUN apt-get update && apt-get install -y tini && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

ENV PORT=7860

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user src/  ./src/
COPY --chown=user data/ ./data/
COPY --chown=user docs/assets/ ./docs/assets/

EXPOSE $PORT

# tini as init process + --production for containerised deployment
ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "solara run src/app.py --host=0.0.0.0 --port=$PORT --production"]
