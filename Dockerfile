from python:3.11-bullseye

RUN mkdir -p /app/aerodata
COPY ./requirements.txt /app/aerodata/requirements.txt
RUN pip install -r /app/aerodata/requirements.txt

COPY ./aerodata /app/aerodata

ENV PYTHONPATH /app
WORKDIR /app/aerodata
CMD ./start.sh
