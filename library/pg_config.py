#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2016, Jony Vesterman Cohen <cohenjo@hpe.com>
#

DOCUMENTATION = '''
---
module: pg_config
short_description: Manage entries in postgresql.conf.
description:
    - This module manipulates postgresql configuration entries and optionally performs a C(pg_ctl reload) after changing them.
version_added: "1.0"
options:
    name:
        description:
            - The dot-separated path (aka I(key)) specifying the sysctl variable.
        required: true
        default: null
        aliases: [ 'key' ]
    value:
        description:
            - Desired value of the sysctl key.
        required: false
        default: null
        aliases: [ 'val' ]
    state:
        description:
            - Whether the entry should be present or absent in the sysctl file.
        choices: [ "present", "absent" ]
        default: present
    ignoreerrors:
        description:
            - Use this option to ignore errors about unknown keys.
        choices: [ "yes", "no" ]
        default: no
    reload:
        description:
            - If C(yes), performs a I(/sbin/sysctl -p) if the C(sysctl_file) is
              updated. If C(no), does not reload I(sysctl) even if the
              C(sysctl_file) is updated.
        choices: [ "yes", "no" ]
        default: "yes"
    sysctl_file:
        description:
            - Specifies the absolute path to C(sysctl.conf), if not C(/etc/sysctl.conf).
        required: false
        default: /etc/sysctl.conf
    sysctl_set:
        description:
            - Verify token value with the sysctl command and set with -w if necessary
        choices: [ "yes", "no" ]
        required: false
        version_added: 1.5
        default: False
notes: []
requirements: []
author: "David CHANIAL (@davixx) <david.chanial@gmail.com>"
'''

EXAMPLES = '''
# Set wal_level to hot_standby in postgresql.conf
- pg_config:
    name: wal_level
    value: hot_standby
    state: present

# Remove kernel.panic entry from /etc/sysctl.conf
- sysctl:
    name: kernel.panic
    state: absent
    sysctl_file: /etc/sysctl.conf

# Set kernel.panic to 3 in /tmp/test_sysctl.conf
- sysctl: name=kernel.panic value=3 sysctl_file=/tmp/test_sysctl.conf reload=no

# Set ip forwarding on in /proc and do not reload the sysctl file
- sysctl: name="net.ipv4.ip_forward" value=1 sysctl_set=yes

# Set ip forwarding on in /proc and in the sysctl file and reload if necessary
- sysctl: name="net.ipv4.ip_forward" value=1 sysctl_set=yes state=present reload=yes
'''

# ==============================================================

import os
import tempfile
import re

# try:
#     import psycopg2
#     import psycopg2.extras
# except ImportError:
#     postgresqldb_found = False
# else:
#     postgresqldb_found = True

class PgConfigModule(object):

    def __init__(self, module):
        self.module = module
        self.args = self.module.params

        self.pgctl_cmd = self.module.get_bin_path('pg_ctl', required=True)
        self.pgconf_file = self.args['pgconf_file']

        self.proc_value = None  # current token value in proc fs
        self.file_value = None  # current token value in file
        self.file_lines = []    # all lines in the file
        self.file_values = {}   # dict of token values

        self.changed = False    # will change occur
        self.set_proc = False   # does sysctl need to set value
        self.write_file = False # does the sysctl file need to be reloaded

        self.process()

    # ==============================================================
    #   LOGIC
    # ==============================================================

    def process(self):

        self.platform = get_platform().lower()

        # Whitespace is bad
        self.args['name'] = self.args['name'].strip()
        self.args['value'] = self._parse_value(self.args['value'])

        thisname = self.args['name']

        # get the current proc fs value
        self.proc_value = self.get_token_curr_value(thisname)

        # get the currect sysctl file value
        self.read_pgconf_file()
        if thisname not in self.file_values:
            self.file_values[thisname] = None

        # update file contents with desired token/value
        self.fix_lines()

        # what do we need to do now?
        if self.file_values[thisname] is None and self.args['state'] == "present":
            self.changed = True
            self.write_file = True
        elif self.file_values[thisname] is None and self.args['state'] == "absent":
            self.changed = False
        elif self.file_values[thisname] != self.args['value']:
            self.changed = True
            self.write_file = True

        # use the sysctl command or not?
        if self.args['pgconf_set']:
            if self.proc_value is None:
                self.changed = True
            elif not self._values_is_equal(self.proc_value, self.args['value']):
                self.changed = True
                self.set_proc = True

        # Do the work
        if not self.module.check_mode:
            if self.write_file:
                self.write_pgconf()
            if self.write_file and self.args['reload']:
                self.reload_pgctl()
            if self.set_proc:
                self.set_token_value(self.args['name'], self.args['value'])

    def _values_is_equal(self, a, b):
        """Expects two string values. It will split the string by whitespace
        and compare each value. It will return True if both lists are the same,
        contain the same elements and the same order."""
        if a is None or b is None:
            return False

        a = a.split()
        b = b.split()

        if len(a) != len(b):
            return False

        return len([i for i, j in zip(a, b) if i == j]) == len(a)

    def _parse_value(self, value):
        if value is None:
            return ''
        elif isinstance(value, bool):
            if value:
                return '1'
            else:
                return '0'
        elif isinstance(value, basestring):
            if value.lower() in BOOLEANS_TRUE:
                return '1'
            elif value.lower() in BOOLEANS_FALSE:
                return '0'
            else:
                return value.strip()
        else:
            return value

    # ==============================================================
    #   SYSCTL COMMAND MANAGEMENT
    # ==============================================================

    # Use the sysctl command to find the current value
    def get_token_curr_value(self, token):
        thiscmd = 'psql -t -c "show %s"' % ( token )
        rc,out,err = self.module.run_command(thiscmd)
        if rc != 0:
            return None
        else:
            return out

    # Use the sysctl command to set the current value
    def set_token_value(self, token, value):
        thiscmd = 'psql -t -c "ALTER SYSTEM SET %s = %s"' % ( token, value)
        rc,out,err = self.module.run_command(thiscmd)
        if rc != 0:
            self.module.fail_json(msg='setting %s failed: %s' % (token, out + err))
        else:
            return rc

    # Run pg_ctl reload
    def reload_pgctl(self, data_dir=None):
        # do it
        if (data_dir==None):
            thiscmd = "%s reload -s " % (self.pgctl_cmd)
        else:
            thiscmd = "%s reload -s -D %s" % (self.pgctl_cmd, data_dir)
        rc,out,err = self.module.run_command(thiscmd)

        if rc != 0:
            self.module.fail_json(msg="Failed to reload pg_ctl: %s" % str(out) + str(err))

    # ==============================================================
    #   SYSCTL FILE MANAGEMENT
    # ==============================================================

    # Get the token value from the sysctl file
    def read_pgconf_file(self):

        lines = []
        if os.path.isfile(self.pgconf_file):
            try:
                f = open(self.pgconf_file, "r")
                lines = f.readlines()
                f.close()
            except IOError:
                e = get_exception()
                self.module.fail_json(msg="Failed to open %s: %s" % (self.sysctl_file, str(e)))

        for line in lines:
            line = line.strip()
            self.file_lines.append(line)

            # don't split empty lines or comments
            if not line or line.startswith("#"):
                continue

            k, v = line.split('=',1)
            k = k.strip()
            v = v.strip()
            self.file_values[k] = v.strip()

    # Fix the value in the sysctl file content
    def fix_lines(self):
        checked = []
        self.fixed_lines = []
        for line in self.file_lines:
            if not line.strip() or line.strip().startswith("#"):
                self.fixed_lines.append(line)
                continue
            tmpline = line.strip()
            k, v = line.split('=',1)
            k = k.strip()
            v = v.strip()
            if k not in checked:
                checked.append(k)
                if k == self.args['name']:
                    if self.args['state'] == "present":
                        new_line = "%s=%s\n" % (k, self.args['value'])
                        self.fixed_lines.append(new_line)
                else:
                    new_line = "%s=%s\n" % (k, v)
                    self.fixed_lines.append(new_line)

        if self.args['name'] not in checked and self.args['state'] == "present":
            new_line = "%s=%s\n" % (self.args['name'], self.args['value'])
            self.fixed_lines.append(new_line)

    # Completely rewrite the sysctl file
    def write_pgconf(self):
        # open a tmp file
        fd, tmp_path = tempfile.mkstemp('.conf', '.ansible_m_pgconf_', os.path.dirname(self.pgconf_file))
        f = open(tmp_path,"w")
        try:
            for l in self.fixed_lines:
                f.write(l.strip() + "\n")
        except IOError:
            e = get_exception()
            self.module.fail_json(msg="Failed to write to file %s: %s" % (tmp_path, str(e)))
        f.flush()
        f.close()

        # replace the real one
        self.module.atomic_move(tmp_path, self.pgconf_file)


# ==============================================================
# main

def main():

    # defining module
    # TODO: how to input $PGDATA/
    module = AnsibleModule(
        argument_spec = dict(
            name = dict(aliases=['key'], required=True),
            value = dict(aliases=['val'], required=False, type='str'),
            state = dict(default='present', choices=['present', 'absent']),
            reload = dict(default=True, type='bool'),
            pgconf_set = dict(default=False, type='bool'),
            ignoreerrors = dict(default=False, type='bool'),
            pgconf_file = dict(default='postgresql.conf', type='path')
        ),
        supports_check_mode=True
    )

    result = PgConfigModule(module)

    module.exit_json(changed=result.changed)

# import module snippets
from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
