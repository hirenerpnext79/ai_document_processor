import requests
import frappe

class GroqService:
    def __init__(self, provider_doc):
        self.api_key = provider_doc.get_password("api_key")
        self.model = provider_doc.model or "llama3-8b-8192"
        self.base_url = provider_doc.base_url or "https://api.groq.com/openai/v1"

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
        
        response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        
        return response.json()['choices'][0]['message']['content']
