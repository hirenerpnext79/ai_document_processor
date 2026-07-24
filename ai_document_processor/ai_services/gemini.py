import requests
import frappe

class GeminiService:
    def __init__(self, provider_doc):
        self.api_key = provider_doc.get_password("api_key")
        self.model = provider_doc.model or "gemini-1.5-flash"
        self.base_url = provider_doc.base_url or "https://generativelanguage.googleapis.com/v1beta"

    def generate(self, text, prompt):
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json"
        }
        
        system_instruction = "You are a helpful assistant. Always return JSON. The JSON should contain title, summary, hashtags (array of strings), and keywords (array of strings)."
        user_message = f"{prompt}\n\nDocument Text:\n{text}"
        
        data = {
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [{
                "parts": [{"text": user_message}]
            }],
            "generationConfig": {
                "response_mime_type": "application/json"
            }
        }

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        text_content = result['candidates'][0]['content']['parts'][0]['text']
        usage = result.get('usageMetadata', {})
        return text_content, usage
