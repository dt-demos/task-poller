#!/bin/bash

addtask() {
    HOST_URL="http://localhost:5000"
    PAYLOAD='
    {
        "project": "slo-demo",
        "service": "casdemoapp",
        "stage": "production",
        "type": "sh.keptn.event.production.getslo.triggered",
        "taskid": "'$2'",
        "runid": "'$2'"
    }
    '

    curl -X POST "$HOST_URL/addtask" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD"

    echo ""

}

