#!/bin/bash
#
# deploy.sh - copy pix web files to the gallery directory
#
# Usage: ./deploy.sh [destination]
#
# Default destination is set below.  Override on the command line, e.g.:
#   ./deploy.sh /var/www/html/othergallery

DEST="${1:-/var/www/html/photos}"

FILES="index.html pix.js pix.css pix-init.pl pix-init.cgi pix-auth.cgi"

echo "Deploying pix to $DEST ..."

# Use sudo only if the destination is not writable by the current user
if [ -w "$DEST" ]; then
    INSTALL="cp"
else
    INSTALL="sudo cp"
fi

for f in $FILES; do
    $INSTALL "$f" "$DEST/$f" && echo "  $f" || { echo "  FAILED: $f"; exit 1; }
done

# Ensure scripts are executable
if [ -w "$DEST" ]; then
    chmod +x "$DEST/pix-init.pl" "$DEST/pix-init.cgi" "$DEST/pix-auth.cgi"
else
    sudo chmod +x "$DEST/pix-init.pl" "$DEST/pix-init.cgi" "$DEST/pix-auth.cgi"
fi

echo "Done."
