#!/bin/bash

docker image build -t aerodata .
docker container run -d --name aerodata -p 8090:8090 -v $(pwd)/aerodata:/app/aerodata aerodata
