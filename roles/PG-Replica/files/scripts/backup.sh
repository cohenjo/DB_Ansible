#!/bin/bash
# postgres backup.sh
#
# to be run on : slave node
# uses ebs snapshots.

psql -h master -c 'SELECT pg_start_backup(''label'', true);'

# EBS snapshot

psql -h master -c 'SELECT * FROM pg_xlogfile_name_offset(pg_stop_backup());'
# output like:
#        file_name         | file_offset
#--------------------------+-------------
# 00000001000000000000000D |     4039624
#
#
# Wal-E - archive master - should happen by itself.
