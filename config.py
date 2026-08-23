import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    DATABASE_NAME = 'triageflow'
    SECRET_KEY = os.getenv('SECRET_KEY', 'triageflow-secret-key-change-in-production')
    
    # AI Provider: 'nvidia' (default) or 'openai'
    AI_PROVIDER = os.getenv('AI_PROVIDER', 'nvidia')
    
    # NVIDIA NIM settings
    NVIDIA_API_KEY = os.getenv('NVIDIA_API_KEY', '')
    NVIDIA_BASE_URL = os.getenv('NVIDIA_BASE_URL', 'https://integrate.api.nvidia.com/v1')
    NVIDIA_MODEL = os.getenv('NVIDIA_MODEL', 'meta/llama-3.3-70b-instruct')
    
    # OpenAI settings (used when AI_PROVIDER=openai)
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    
    @classmethod
    def get_ai_key(cls):
        """Return the active API key based on the selected provider."""
        if cls.AI_PROVIDER == 'openai':
            return cls.OPENAI_API_KEY
        return cls.NVIDIA_API_KEY
    
    @classmethod
    def get_ai_base_url(cls):
        """Return the active base URL based on the selected provider."""
        if cls.AI_PROVIDER == 'openai':
            return cls.OPENAI_BASE_URL
        return cls.NVIDIA_BASE_URL
    
    @classmethod
    def get_ai_model(cls):
        """Return the active model based on the selected provider."""
        if cls.AI_PROVIDER == 'openai':
            return cls.OPENAI_MODEL
        return cls.NVIDIA_MODEL