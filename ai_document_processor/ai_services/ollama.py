import requests
import frappe

class OllamaService:
    def __init__(self, provider_doc):
        self.model = provider_doc.model or "llama3"
        self.base_url = provider_doc.base_url or "http://localhost:11434/api"

    def generate(self, text, prompt):
        url = f"{self.base_url}/generate"
        headers = {
            "Content-Type": "application/json"
        }
        
        system_prompt = "You are a helpful assistant. Always return JSON. The JSON should contain title, summary, hashtags (array of strings), and keywords (array of strings)."
        full_prompt = f"{system_prompt}\n\nTask: {prompt}\n\nDocument Text:\n{text}"
        
        data = {
            "model": self.model,
            "prompt": full_prompt,
            "format": "json",
            "stream": False
        }
        
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        text_content = result.get('response', '')
        usage = {
            "prompt_eval_count": result.get("prompt_eval_count"),
            "eval_count": result.get("eval_count"),
            "total_duration": result.get("total_duration")
        }
        return text_content, usage

