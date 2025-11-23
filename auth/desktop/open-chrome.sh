#!/usr/bin/env bash

sudo -u abc rm -f /profile/Singleton*
sudo -u abc google-chrome \
    --user-data-dir=/profile \
    --no-first-run \
    --password-store=basic \
    --use-mock-keychain \
    --disable-dev-shm-usage \
    --disable-gpu \
    --no-sandbox \
    https://photos.google.com
