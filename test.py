import os
from pprint import pprint
os.environ.setdefault('CLOUDCIX_SETTINGS_MODULE', 'test_settings')
from cloudcix.api.compute import Compute
from cloudcix.auth import get_admin_token

TOKEN = get_admin_token()


def api_read(client, pk, **kwargs):
    response = client.read(
        token=TOKEN,
        pk=pk,
        **kwargs,
    )
    if response.status_code != 200:
        print(response.json())
        return None
    else:
        return response.json()['content']


def api_list(client, params, **kwargs):
    response = client.list(
        token=TOKEN,
        params=params,
        **kwargs,
    )
    if response.status_code != 200:
        print(response.json())
    else:
        print(response.json()['content'])


if __name__ == '__main__':
    vm = api_read(Compute.vm, pk=1156)
    pprint(vm)
    #server = api_read(Compute.server, pk=16)
    #pprint(server)
