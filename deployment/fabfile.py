"""Robot Deployment Script"""
import os
from fabric.api import *
from fabric.contrib import console

env.project = "robot"
env.user = "administrator"
env.forward_agent = True

@task
def staging():
    """
    Setup the staging environment (Robot Alpha)
    :usage: `fab staging <cmd>`
    """
    env.environment = 'staging'
    env.hosts = ['2a02:2078:3::3']
    env.branch = 'master'
    env.home = '/home/administrator'
    setup()

def setup():
    """Setup the required paths for fabric to deploy to"""
    env.root = os.path.join(env.home, env.project)

@task
def deploy():
    require('root', provided_by=('staging', 'live'))
    require('branch', provided_by=('staging', 'live'))
    with cd(env.root):
        run('git fetch origin')
        run('git reset --hard origin/%(branch)s' % env)
        run('pip install -U -r requirements.txt')

