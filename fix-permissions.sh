#!/bin/bash
# Fix permissions for all profile and photos directories

PUID=${1:-1000}
PGID=${2:-1000}

echo "Fixing permissions for PUID=$PUID PGID=$PGID"

# Find all profile and photos directories
for dir in profile* photos*; do
    if [ -d "$dir" ]; then
        echo "Fixing $dir..."
        sudo chown -R $PUID:$PGID "$dir"
        sudo chmod -R 755 "$dir"
    fi
done

echo "Done! Permissions fixed."
