#!/bin/bash
# Poll until current job finishes, then submit next batch of 35
# All 35 have both R1 and R2 human annotations

API="http://localhost:9005/api/jobs"
CURRENT_JOB="dbc48eb94a68"

while true; do
    STATUS=$(curl -s "$API/$CURRENT_JOB" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)

    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ]; then
        echo "$(date): Job $CURRENT_JOB finished with status: $STATUS. Submitting next batch..."
        RESULT=$(curl -s -X POST "$API" \
            -H "Content-Type: application/json" \
            -d '{"nct_ids": ["NCT00000391","NCT00000392","NCT00000393","NCT00000435","NCT00000775","NCT00000795","NCT00000798","NCT00000846","NCT00000886","NCT00001060","NCT00001118","NCT00001386","NCT00001439","NCT00001564","NCT00001685","NCT00001703","NCT00001705","NCT00001827","NCT00001832","NCT00002083","NCT00002228","NCT00002363","NCT00002428","NCT00004358","NCT00004494","NCT00004984","NCT00005779","NCT00013910","NCT00027131","NCT00028431","NCT00031044","NCT00032045","NCT00034255","NCT00039000","NCT00042497"]}')
        echo "$(date): Submit result: $RESULT"
        exit 0
    fi

    echo "$(date): Job $CURRENT_JOB still $STATUS. Checking again in 2 minutes..."
    sleep 120
done
