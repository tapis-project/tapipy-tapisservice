#!/bin/bash

export PYTHONPATH=$PYTHONPATH:/home/tapis
cd /home/tapis/service; /usr/local/bin/gunicorn -k $workerCls -w $processes --threads $threads -b :5000 api:app

if [$DEBUG_SLEEP_LOOP == "sleep"]; then
  while true; do sleep 86400; done
fi
