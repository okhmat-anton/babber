import httpx
import os
async def execute(folder='inbox', search=None, is_read=None, limit=50, page=1):
    api_key = os.environ.get('AKM_ADVISOR_API_KEY', '')
    base_url = os.environ.get('AKM_ADVISOR_URL', '').rstrip('/')
    if not api_key or not base_url:
        return {'error': 'AKM Advisor API key/URL not configured.'}
    headers = {'X-Agent-Key': api_key}
    params = {'folder': folder, 'limit': min(limit, 200), 'page': page}
    if search:
        params['search'] = search
    if is_read is not None:
        params['is_read'] = str(is_read).lower()
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        r = await client.get(f'{base_url}/email/messages', headers=headers, params=params)
        if r.status_code != 200:
            return {'error': f'API error {r.status_code}: {r.text[:500]}'}
        data = r.json()
        return {'emails': data.get('items', []), 'total': data.get('total', 0), 'page': data.get('page', page), 'pages': data.get('pages', 0)}
