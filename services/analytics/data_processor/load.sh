#!/bin/bash
./wait-for-it.sh -t 30 ${KAFKA_BOOTSTRAP_SERVERS}

if [ "$RUN_ARG" = "realtime" ] ; then
  echo 'candles RT processor starting!'
  python application.py consume-rt
elif [ "$RUN_ARG" = "batch" ] ; then
  echo 'candles batch processor starting!'
  python application.py consume-batch
else
  echo 'UNKNOWN COMMAND!'
fi
