#!/bin/bash

sudo groupmod --gid $PGID abc
sudo usermod --uid $PUID --gid $PGID abc
sudo chown -R abc:abc /home/abc
sudo chown -R abc:abc /profile

/startup.sh "$@"