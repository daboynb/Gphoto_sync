#!/bin/bash

sudo groupmod --gid $PGID abc
sudo usermod --uid $PUID --gid $PGID abc
sudo chown -R abc:abc /home/abc
sudo chown -R abc:abc /profile

# Copy open-chrome.sh to Desktop after volume is mounted
sudo cp /tmp/open-chrome.sh /home/abc/Desktop/open-chrome.sh
sudo chmod +x /home/abc/Desktop/open-chrome.sh
sudo chown abc:abc /home/abc/Desktop/open-chrome.sh

/startup.sh "$@"