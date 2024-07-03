FROM python:3.11

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

#RUN API_URL=https://cardanoism.com:8000 reflex export --no-zip

STOPSIGNAL SIGKILL

CMD reflex run --env prod