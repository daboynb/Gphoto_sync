#!/bin/bash
# Script to add a new locale to months-config.json
# Usage: ./add-locale-to-config.sh <output-from-console-extract.js>
#
# Example:
# 1. Run console-extract.js in Google Photos console
# 2. Copy the output
# 3. Paste it when prompted by this script

set -e

CONFIG_FILE="gphotos-cdp/months-config.json"

echo "=== Add Locale to months-config.json ==="
echo ""
echo "Paste the output from console-extract.js (press Ctrl+D when done):"
echo ""

# Read all input
INPUT=$(cat)

# Extract values using grep/sed
METADATA=$(echo "$INPUT" | grep "METADATA_FORMAT:" -A 1 | tail -1 | xargs)
MONTHS=$(echo "$INPUT" | grep "MONTHS:" -A 1 | tail -1 | xargs)
DATE_FORMAT=$(echo "$INPUT" | grep "DATE_FORMAT:" | cut -d: -f2- | xargs)
DETECTED_LOCALE=$(echo "$INPUT" | grep "DETECTED_LOCALE:" | cut -d: -f2 | xargs)
PAGE_LANG=$(echo "$INPUT" | grep "PAGE_LANG:" | cut -d: -f2 | xargs)

if [ -z "$PAGE_LANG" ] || [ -z "$MONTHS" ]; then
    echo "❌ Error: Could not parse input. Make sure you copied the complete output."
    exit 1
fi

echo ""
echo "Parsed data:"
echo "  Language: $PAGE_LANG"
echo "  Months: $MONTHS"
echo "  Metadata: $METADATA"
echo "  Format: $DATE_FORMAT"
echo ""

# Convert comma-separated months to JSON array
MONTHS_JSON=$(echo "$MONTHS" | sed 's/, */", "/g' | sed 's/^/["/' | sed 's/$/"]/')

# Create JSON entry
NEW_ENTRY=$(cat <<EOF
  "$PAGE_LANG": {
    "months": $MONTHS_JSON,
    "metadataFormat": "$METADATA",
    "dateFormat": "$DATE_FORMAT"
  }
EOF
)

# Check if locale already exists
if grep -q "\"$PAGE_LANG\":" "$CONFIG_FILE"; then
    echo "⚠️  Locale '$PAGE_LANG' already exists in config."
    read -p "Overwrite? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi

    # Remove old entry (using a temp file for safety)
    TMP_FILE=$(mktemp)
    # This removes the old locale block
    python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    data = json.load(f)
data['$PAGE_LANG'] = {
    'months': $MONTHS_JSON,
    'metadataFormat': '$METADATA',
    'dateFormat': '$DATE_FORMAT'
}
with open('$TMP_FILE', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
"
    mv "$TMP_FILE" "$CONFIG_FILE"
    echo "✅ Updated locale '$PAGE_LANG' in $CONFIG_FILE"
else
    # Add new entry
    TMP_FILE=$(mktemp)
    python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    data = json.load(f)
data['$PAGE_LANG'] = {
    'months': $MONTHS_JSON,
    'metadataFormat': '$METADATA',
    'dateFormat': '$DATE_FORMAT'
}
with open('$TMP_FILE', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
"
    mv "$TMP_FILE" "$CONFIG_FILE"
    echo "✅ Added locale '$PAGE_LANG' to $CONFIG_FILE"
fi

echo ""
echo "Current locales in config:"
python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    data = json.load(f)
for lang in data.keys():
    print(f'  - {lang}: {', '.join(data[lang]['months'])}')
"
