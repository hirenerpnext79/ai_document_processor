import frappe
from frappe import _
from .openai import OpenAIService
from .gemini import GeminiService
from .ollama import OllamaService
from .groq import GroqService
from .openrouter import OpenRouterService
import json

def get_service_class(provider_name):
    services = {
        'OpenAI': OpenAIService,
        'Gemini': GeminiService,
        'Ollama': OllamaService,
        'Groq': GroqService,
        'OpenRouter': OpenRouterService
    }
    return services.get(provider_name)

def generate(provider_doc, prompt_doc, text):
    service_class = get_service_class(provider_doc.provider)
    if not service_class:
        frappe.throw(_("Provider {0} is not supported").format(provider_doc.provider))
        
    service = service_class(provider_doc)
    return service.generate(text, prompt_doc.prompt)
