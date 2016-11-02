#!/usr/bin/env bash
set -u
set -e

# Configurable items
PGBOUNCER_HOSTS="node1 node2 node3"
REPMGR_DB="repmgr"
REPMGR_USER="repmgr"
REPMGR_SCHEMA="repmgr_test"
PGBOUNCER_CONFIG="/etc/pgbouncer.ini"
PGBOUNCER_INI_TEMPLATE="/var/lib/pgsql/repmgr/pgbouncer.ini.template"
PGBOUNCER_DATABASE="appdb"

# 1. Pause running pgbouncer instances
for HOST in $PGBOUNCER_HOSTS
do
    psql -t -c "pause" -h $HOST -p $PORT -U postgres pgbouncer
done


# 2. Promote this node from standby to master

repmgr standby promote -f /etc/repmgr.conf


# 3. Reconfigure pgbouncer instances

PGBOUNCER_INI_NEW="/tmp/pgbouncer.ini.new"

for HOST in $PGBOUNCER_HOSTS
do
    # Recreate the pgbouncer config file
    echo -e "[databases]\n" > $PGBOUNCER_INI_NEW

    psql -d $REPMGR_DB -U $REPMGR_USER -t -A \
      -c "SELECT '$PGBOUNCER_DATABASE= ' || conninfo || ' application_name=pgbouncer_$HOST' \
          FROM $REPMGR_SCHEMA.repl_nodes \
          WHERE active = TRUE AND type='master'" >> $PGBOUNCER_INI_NEW

    cat $PGBOUNCER_INI_TEMPLATE >> $PGBOUNCER_INI_NEW

    rsync $PGBOUNCER_INI_NEW $HOST:$PGBOUNCER_CONFIG

    psql -tc "reload" -h $HOST -U postgres pgbouncer
    psql -tc "resume" -h $HOST -U postgres pgbouncer

done

# Clean up generated file
rm $PGBOUNCER_INI_NEW

echo "Reconfiguration of pgbouncer complete"
