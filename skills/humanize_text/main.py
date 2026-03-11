import httpx
from app.config import settings
from app.database import get_mongodb
from app.mongodb.services import ModelConfigService
async def execute(text, tone='neutral', **kwargs):
    db = get_mongodb()
    mc_svc = ModelConfigService(db)
    # Try to find a model with 'base' role
    mc = await mc_svc.find_one({'role': 'base'})
    model_id = mc.model_id if mc else 'llama3.1:8b'
    system_prompt = (
        'You are a writing editor that identifies and removes signs of AI-generated text. '
        'Your job: take the input text and rewrite it to sound human and natural.\n\n'
        '## The 24 AI Patterns to Remove\n'
        '### Content\n'
        '1. No significance inflation — no grandiose claims about importance\n'
        '2. No notability name-dropping — no inserting famous names without substance\n'
        '3. No superficial -ing openers — no "Understanding the landscape" style starts\n'
        '4. No promotional language — no "game-changing" or "revolutionary"\n'
        '5. No vague attributions — no "experts say" without specifics\n'
        '6. No formulaic challenges — no "The challenge lies in..."\n'
        '### Language\n'
        '7. No AI vocabulary — avoid: Additionally, Crucial, Delve, Enhance, Foster, '
        'Landscape (metaphorical), Pivotal, Showcase, Tapestry, Testament, Underscore, '
        'Vibrant, Multifaceted, Comprehensive, Leverage, Innovative, Utilize, Navigate '
        '(metaphorical), Paradigm, Robust\n'
        '8. Use simple verbs — is/are/has/shows/means\n'
        '9. No negative parallelisms — no "not just X but Y"\n'
        '10. No rule-of-three — vary groupings\n'
        '11. No synonym cycling — say it once, clearly\n'
        '12. No false ranges — no "from X to Y" for fake comprehensiveness\n'
        '### Style\n'
        '13. Minimal em dashes — at most one per 500 words\n'
        '14. No bold-for-emphasis overuse\n'
        '15. No inline-header lists with bold lead-ins\n'
        '16. Sentence case headings\n'
        '17. No gratuitous emoji\n'
        '18. Straight quotes\n'
        '### Communication\n'
        '19. No chatbot artifacts like "Great question!"\n'
        '20. No cutoff disclaimers\n'
        '21. No sycophantic tone — no praising the user\n'
        '### Filler\n'
        '22. No filler phrases like "It\'s important to note"\n'
        '23. No excessive hedging\n'
        '24. No generic conclusions like "In conclusion"\n\n'
        '### Soul\n'
        '- Vary sentence length\n'
        '- Have opinions when appropriate\n'
        '- Use first person naturally\n'
        '- Acknowledge complexity\n'
        '- Be specific, not generic\n\n'
        'Tone: ' + tone + '\n\n'
        'Process: Identify AI patterns → rewrite → preserve meaning → add soul → '
        'anti-AI audit (ask "what makes this obviously AI?") → second rewrite.\n\n'
        'Output ONLY the rewritten text. No explanations, no preamble.'
    )
    ollama_url = settings.OLLAMA_BASE_URL
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f'{ollama_url}/api/chat',
            json={'model': model_id, 'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': text},
            ], 'stream': False},
        )
        if resp.status_code != 200:
            return {'error': f'LLM error {resp.status_code}: {resp.text[:500]}'}
        data = resp.json()
        result = data.get('message', {}).get('content', '')
    return {'original_length': len(text), 'humanized_length': len(result), 'text': result}
