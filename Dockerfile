FROM python:3.11

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

#RUN API_URL=https://cardanoism.com:8000 reflex export --no-zip

# Download all npm dependencies and compile frontend
RUN API_URL=https://cardanoism.com:8000 reflex export --frontend-only --no-zip && mv .web/_static/* /srv/ && rm -rf .web

STOPSIGNAL SIGKILL

CMD reflex run --env prod --backend-only --loglevel debug