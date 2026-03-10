import httpx
import os
async def execute():
    api_key = os.environ.get('AKM_ADVISOR_API_KEY', '')
    base_url = os.environ.get('AKM_ADVISOR_URL', '').rstrip('/')
    if not api_key or not base_url:
        return {'error': 'AKM Advisor API key/URL not configured.'}
    headers = {'X-Agent-Key': api_key}
    async with httpx.AsyncClient(timeout=20, verify=False) as client:
        r = await client.get(f'{base_url}/email/stats', headers=headers)
        if r.status_code != 200:
            return {'error': f'API error {r.status_code}: {r.text[:500]}'}
        return r.json()
