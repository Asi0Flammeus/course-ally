import os
import time
from typing import Optional, Dict, Any
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class AnthropicClient:
    """
    Wrapper for Anthropic API client with error handling and rate limiting.
    """
    
    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize the Anthropic client.
        
        Args:
            api_key: Anthropic API key. If None, will read from ANTHROPIC_API_KEY env var.
            max_retries: Maximum number of retries for failed requests.
            retry_delay: Delay between retries in seconds.
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Anthropic API key not found. Please set ANTHROPIC_API_KEY in your .env file "
                "or pass it directly to the constructor."
            )
        
        self.client = Anthropic(api_key=self.api_key)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.model = "claude-opus-4-5-20251101"
    
    def generate_text(
        self, 
        prompt: str, 
        max_tokens: int = 4000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate text using Claude API with retry logic.
        
        Args:
            prompt: The user prompt/message
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation (0.0 to 1.0)
            system_prompt: Optional system prompt
            
        Returns:
            Generated text response
            
        Raises:
            Exception: If all retries fail
        """
        messages = [{"role": "user", "content": prompt}]
        
        for attempt in range(self.max_retries + 1):
            try:
                request_params = {
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": messages
                }
                
                if system_prompt:
                    request_params["system"] = system_prompt
                
                response = self.client.messages.create(**request_params)
                
                # Extract text content from response
                if response.content and len(response.content) > 0:
                    return response.content[0].text
                else:
                    raise ValueError("Empty response from API")
                    
            except Exception as e:
                if attempt == self.max_retries:
                    raise Exception(f"Failed after {self.max_retries + 1} attempts: {str(e)}")
                
                # Wait before retry
                time.sleep(self.retry_delay * (attempt + 1))
                continue
        
        raise Exception("Unexpected error in generate_text")
    
    def get_usage_info(self) -> Dict[str, Any]:
        """
        Get information about API usage and model details.
        
        Returns:
            Dictionary with model and usage information
        """
        return {
            "model": self.model,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "api_key_configured": bool(self.api_key)
        }
