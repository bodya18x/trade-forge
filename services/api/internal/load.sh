#!/bin/bash

echo 'Internal API starting!'
uvicorn app.main:app --host 0.0.0.0 --port 8000
