#!/bin/bash

POLLER_SLEEP_SECONDS=10
URL="http://localhost:5000/process"

echo "Poller calling $URL.  Hit CTRL+C to exit"
while true; 
do 
    curl -X GET "$URL"
    echo ""
    sleep $POLLER_SLEEP_SECONDS; 
done