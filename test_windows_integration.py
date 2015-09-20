# Python
import json
import os
import shutil
import subprocess

# PyYAML
import yaml

# pytest
import pytest

def _run_ansible_playbook(inventory, playbook, tags=None, limit=None, verbosity=2, **extra_vars):
    args = ['ansible-playbook', '-i', inventory]
    if limit:
        args.extend(['-l', limit])
    if tags:
        args.extend(['-t', tags])
    if verbosity:
        args.append('-%s' % ('v' * verbosity))
    if extra_vars:
        args.extend(['-e', json.dumps(extra_vars)])
    args.append(playbook)
    rc = subprocess.call(args)
    assert rc == 0

def _get_integration_tests_path():
    import ansible
    path = os.path.join(os.path.dirname(ansible.__file__), '..', '..', 'test', 'integration')
    return os.path.normpath(os.path.abspath(path))

@pytest.fixture(scope='session')
def integration_tests_path(request):
    return _get_integration_tests_path()

@pytest.fixture(scope='session')
def windows_versions(request):
    return [
        'server-2008',
        'server-2008-r2',
        'server-2012',
        'server-2012-r2',
    ]

@pytest.fixture(scope='session')
def windows_roles(request, integration_tests_path=None):
    roles = []
    integration_tests_path = integration_tests_path or _get_integration_tests_path()
    for make_target in ('test_winrm', 'test_winrm_extras'):
        test_winrm_path = os.path.join(integration_tests_path, '%s.yml' % make_target)
        if not os.path.exists(test_winrm_path):
            continue
        with open(test_winrm_path) as f:
            data = yaml.safe_load(f)
        try:
            for role in data[0]['roles']:
                if not isinstance(role, dict):
                    continue
                if 'role' not in role or 'tags' not in role:
                    continue
                # (make target, role name, role tag)
                roles.append((make_target, role['role'], role['tags']))
        except (IndexError, KeyError):
            pass
    return roles

def pytest_generate_tests(metafunc):
    if 'windows_version' in metafunc.fixturenames:
        metafunc.parametrize('windows_version', windows_versions(None), scope='session')
    if 'windows_tag' in metafunc.fixturenames or 'make_target' in metafunc.fixturenames:
        roles = windows_roles(None)
        argvalues = [(x[0], x[2]) for x in roles]
        ids = [x[1] for x in roles]
        metafunc.parametrize(['make_target', 'windows_tag'], argvalues, ids=ids, scope='session')

@pytest.fixture(scope='session')
def windows_inventory(request):
    inventory_file = 'inventory.windows-qa'
    if not os.path.exists(inventory_file):
        _run_ansible_playbook('inventory.local', 'testenv.yml', tags='setup')
    assert os.path.exists(inventory_file)
    def cleanup():
        _run_ansible_playbook('inventory.local', 'testenv.yml', tags='cleanup')
    request.addfinalizer(cleanup)
    return inventory_file

@pytest.fixture(scope='session')
def windows_limit(windows_inventory, windows_version):
    limit = 'windows-qa-%s' % windows_version
    args = ['ansible', '-i', windows_inventory, limit, '--list-hosts']
    hosts_output = subprocess.check_output(args).strip()
    if 'hosts (0)' in hosts_output:
        pytest.skip('no host found matching limit "%s"' % limit)
    return limit

@pytest.fixture(scope='session')
def inventory_winrm(integration_tests_path, windows_inventory):
    inventory_winrm_path = os.path.join(integration_tests_path, 'inventory.winrm')
    shutil.copyfile(windows_inventory, inventory_winrm_path)
    assert os.path.exists(inventory_winrm_path)
    return inventory_winrm

def test_win_role(integration_tests_path, inventory_winrm, make_target, windows_limit, windows_tag):
    env = dict(os.environ.items())
    env['TEST_FLAGS'] = '-t %s -l %s -vvv' % (windows_tag, windows_limit)
    args = ['make', make_target]
    rc = subprocess.call(args, env=env, cwd=integration_tests_path)
    assert rc == 0
