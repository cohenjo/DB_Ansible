#!/bin/bash
# file: pgbouncer.sh
# this file preforms basic configuration for pgbouncer connection configuration.
user=pgbouncer;
passw=pgbouncer_admin1234;
pswd=`echo -n md5; echo $passwd$user | md5sum`
cat > /etc/pgbouncer/users.auth <<EOF
"$user" "$pswd" ""
EOF

psql -d developer_ems <<EOF
CREATE USER pgbouncer;
CREATE SCHEMA pgbouncer;
CREATE OR REPLACE FUNCTION pgbouncer.user_lookup(in i_username text, out uname text, out phash text)
RETURNS record AS $$
BEGIN
    SELECT usename, passwd FROM pg_catalog.pg_shadow
    WHERE usename = i_username INTO uname, phash;
    RETURN;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
REVOKE ALL ON FUNCTION pgbouncer.user_lookup(text) FROM public, pgbouncer;
GRANT EXECUTE ON FUNCTION pgbouncer.user_lookup(text) TO pgbouncer;
GRANT USAGE on schema pgbouncer to pgbouncer;
EOF
