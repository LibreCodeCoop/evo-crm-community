FROM python:3.11-alpine

WORKDIR /app

COPY journeys_mock.py /app/journeys_mock.py

ENV JOURNEYS_STATE_FILE=/data/journeys.json
ENV PORT=8090

VOLUME ["/data"]

EXPOSE 8090

CMD ["python", "/app/journeys_mock.py"]
