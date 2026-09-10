import requests
import frappe

class OpenRouterService:
    def __init__(self, provider_doc):
        self.api_key = provider_doc.get_password("api_key")
        self.model = provider_doc.model or "openai/gpt-3.5-turbo"
        self.base_url = provider_doc.base_url or "https://openrouter.ai/api/v1"

    def generate(self, text, prompt):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": frappe.utils.get_url(),
            "X-Title": "AI Document Processor for ERPNext",
            "Content-Type": "application/json"
        }
        
        system_prompt = "You are a helpful assistant. Always return JSON. The JSON should contain title, summary, hashtags (array of strings), and keywords (array of strings)."
        user_message = f"{prompt}\n\nDocument Text:\n{text}"
        
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "response_format": {"type": "json_object"}
        }
        
        try:
            response = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=data,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            text_content = result['choices'][0]['message']['content']
            usage = result.get('usage', {})
            return text_content, usage
        except requests.exceptions.RequestException as e:
            error_msg = getattr(e.response, 'text', '')
            frappe.log_error(f"OpenRouter API Call Failed: {str(e)}\nResponse: {error_msg}", "AI Document Processor OpenRouter Error")
            raise
