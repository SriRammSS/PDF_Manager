#!/bin/bash
# Fix for macOS fork() + Objective-C crash (NSCharacterSet / pikepdf)
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

cd "$(dirname "$0")/backend"
source .venv/bin/activate
# Use solo pool to avoid fork() crashes with pikepdf on macOS
celery -A app.tasks worker --loglevel=info --pool=solo
