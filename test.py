import os
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
    else:
        print(response.json()['content'])


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
    api_list(Compute.project, params={})
