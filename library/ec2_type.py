#!/usr/bin/python

DOCUMENTATION = '''
---
module: ec2_type
short_description: change ec2 instance type
'''

EXAMPLES = '''
- name: Create a github Repo
  ec2_type:
    region: 'eu-west-1'
    id: 'i-32587dy938'
    profile: 'production_23'
    type: 'r4.2xlarge'
  register: result
'''

from ansible.module_utils.basic import *
import boto.ec2


def cng_inst_type(data):
    id = data['id']
    type = data['type']
    profile = data['profile']
    region = data['region']
    change_instance_type(id,type,region,profile)

    result = {"status": "SUCCESS"}
    return False, True, result


def change_instance_type(id,type='r4.2xlarge',region='eu-west-1',profile='production_84'):
  ec2_conn=boto.ec2.connect_to_region(region,profile_name=profile)
  ec2_conn.modify_instance_attribute(id,'instanceType',type )


def main():

    fields = {
        "region": {"required": True , "type": "str"},
        "id": {"required": True, "type": "str"},
        "profile": {"required": True, "type": 'str'},
        "type": {"default": 'r4.2xlarge', "type": 'str'}
    }


    module = AnsibleModule(argument_spec=fields)
    is_error, has_changed, result = cng_inst_type(module.params)

    if not is_error:
        module.exit_json(changed=has_changed, meta=result)
    else:
        module.fail_json(msg="Error changing type", meta=result)


if __name__ == '__main__':
    main()
