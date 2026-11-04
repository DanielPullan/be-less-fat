#!/bin/bash
# Nightly backup of Be Less Fat's PostgreSQL database: one per weekday (7 days), in ~/belessfat-backups. From the app user's
# crontab:
#   50 2 * * * /home/dan/BeLessFat/blf-app/deploy/backup.sh belessfat
# Argument: the database name (default belessfat). Restore: see docs/server-setup.md.
set -euo pipefail
DB=${1:-belessfat}
OUT=$HOME/belessfat-backups
DAY=$(date +%a)
mkdir -p "$OUT" && chmod 700 "$OUT"
umask 077
pg_dump --format=custom --file="$OUT/$DB-$DAY.dump.tmp" "$DB"
mv "$OUT/$DB-$DAY.dump.tmp" "$OUT/$DB-$DAY.dump"
echo "$(date '+%F %T') backed up $DB to $OUT" >> "$OUT/backup.log"
