#!/bin/bash
. /home/pi/cansat-gs/.venv/bin/activate

export FLASK_APP=/home/pi/cansat-gs/app.py
export FLASK_ENV=development

flask run --host 0.0.0.0 --port 5000
