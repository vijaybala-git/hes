FROM python:3.12-slim

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

ENV PORT=8080

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user src/  ./src/
COPY --chown=user data/ ./data/
COPY --chown=user docs/assets/ ./docs/assets/

EXPOSE $PORT
<<<<<<< HEAD

CMD ["sh", "-c", "solara run src/app.py --host 0.0.0.0 --port $PORT --no-open"]
=======
CMD ["sh", "-c", "solara run src/app.py --host 0.0.0.0 --port $PORT"]
>>>>>>> dcadf3145e21f616f5e62e536a6d84d772a15ccc
