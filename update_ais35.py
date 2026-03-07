import os
import json
import urllib.request

# Load .env.agent
with open('.env.agent') as f:
    for line in f:
        if '=' in line and not line.strip().startswith('#'):
            key, value = line.strip().split('=', 1)
            os.environ[key] = value.strip('"\'')

api_url = os.environ['AGENT_API_URL']
api_key = os.environ['AGENT_API_KEY']

# Read requirements document
with open('ais35_requirements.md') as f:
    description = f.read()

# Get AIS-35 issue ID
req = urllib.request.Request(
    f'{api_url}/issues?limit=20',
    headers={'X-Agent-Key': api_key}
)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read())
    issues = data.get('items', [])
    ais35 = next((i for i in issues if i.get('key') == 'AIS-35'), None)
    if not ais35:
        print('❌ AIS-35 not found')
        exit(1)
    issue_id = ais35['id']
    print(f'Found AIS-35: {issue_id}')

# Update description
update_data = json.dumps({'description': description}).encode('utf-8')

req = urllib.request.Request(
    f'{api_url}/issues/{issue_id}',
    data=update_data,
    headers={
        'X-Agent-Key': api_key,
        'Content-Type': 'application/json'
    },
    method='PATCH'
)

try:
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read())
        print(f'✅ AIS-35 description updated')
        print(f'   Issue: {result["key"]} - {result["summary"]}')
        print(f'   Status: {result["status"]}')
        print(f'   Description length: {len(description)} chars')
except Exception as e:
    print(f'❌ Error updating: {e}')
