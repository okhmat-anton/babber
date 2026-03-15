from app.config import get_settings
from app.database import get_mongodb
from app.services.model_role_service import resolve_model_for_role
from app.api.settings import get_setting_value
from app.llm.base import Message, GenerationParams
from app.llm.ollama import OllamaProvider
from app.llm.anthropic import AnthropicProvider
from app.llm.kieai import KieAIProvider
from app.llm.openai_compatible import OpenAICompatibleProvider


async def execute(text, tone='neutral', **kwargs):
    db = get_mongodb()
    settings = get_settings()

    # Resolve model using the standard fallback chain:
    # exact role 'base' -> first active Ollama -> first active API model
    mc = await resolve_model_for_role(db, 'base')
    if not mc:
        return {'error': 'No LLM model configured. Add a model in Settings > Models.'}

    provider_name = mc.provider
    model_name = mc.model_id
    api_key = mc.api_key
    base_url = mc.base_url

    # Resolve provider-specific settings
    if provider_name == 'ollama':
        base_url = settings.OLLAMA_BASE_URL
    elif provider_name == 'anthropic' and not api_key:
        api_key = await get_setting_value(db, 'anthropic_api_key')
        base_url = base_url or 'https://api.anthropic.com'
    elif provider_name == 'kieai' and not api_key:
        api_key = await get_setting_value(db, 'kieai_api_key')
        base_url = base_url or 'https://api.kie.ai'
    else:
        base_url = base_url or 'https://api.openai.com/v1'

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

    messages = [
        Message(role='system', content=system_prompt),
        Message(role='user', content=text),
    ]
    params = GenerationParams(temperature=0.8, max_tokens=32768)

    # Use the proper LLM provider
    if provider_name == 'ollama':
        llm = OllamaProvider(base_url)
    elif provider_name == 'anthropic':
        llm = AnthropicProvider(api_key=api_key, base_url=base_url)
    elif provider_name == 'kieai':
        llm = KieAIProvider(api_key=api_key, base_url=base_url)
    else:
        llm = OpenAICompatibleProvider(base_url, api_key)

    resp = await llm.chat(model_name, messages, params)
    result = resp.content
    return {'original_length': len(text), 'humanized_length': len(result), 'text': result}
