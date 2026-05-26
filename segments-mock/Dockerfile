FROM python:3.11-alpine

WORKDIR /app

COPY segments_mock.py /app/segments_mock.py

ENV SEGMENTS_STATE_FILE=/data/segments.json
ENV PORT=8091

VOLUME ["/data"]

EXPOSE 8091

CMD ["python", "/app/segments_mock.py"]
