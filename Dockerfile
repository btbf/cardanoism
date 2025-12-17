FROM python:3.12


ENV REDIS_URL=redis://redis PYTHONUNBUFFERED=1
ENV DB_HOST=${DB_HOST} DB_PORT=${DB_PORT} DB_USER=${DB_USER} DB_PASSWORD=${DB_PASSWORD} DB_NAME=${DB_NAME} GPT_API_KEY=${GPT_API_KEY}

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt


ENTRYPOINT ["reflex", "run", "--env", "prod", "--backend-only", "--loglevel", "debug" ]
