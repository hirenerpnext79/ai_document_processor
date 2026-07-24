import requests
import frappe

class OpenAIService:
    def __init__(self, provider_doc):
        self.api_key = provider_doc.get_password("api_key")
        self.model = provider_doc.model
        self.base_url = provider_doc.base_url or "https://api.openai.com/v1"

    def generate(self, text, prompt):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
        
        result = response.json()
        text_content = result['choices'][0]['message']['content']
        usage = result.get('usage', {})
        return text_content, usage
