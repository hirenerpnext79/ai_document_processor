import requests
import frappe

class GroqService:
    def __init__(self, provider_doc):
        self.api_key = provider_doc.get_password("api_key")
        self.model = provider_doc.model or "llama3-8b-8192"
        self.base_url = provider_doc.base_url or "https://api.groq.com/openai/v1/chat/completions"

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
        response = requests.post(self.base_url, headers=headers, json=data)
        if response.status_code != 200:
            frappe.throw(f"Groq API Error: {response.text}")
        
        result = response.json()
        if 'choices' not in result:
            frappe.throw(f"Invalid response from Groq API: {result}")
        text_content = result['choices'][0]['message']['content']
        usage = result.get('usage', {})
        return text_content, usage