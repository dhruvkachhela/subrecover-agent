# How this works:
# This configuration module loads environment variables from the .env file.
# It defines a Config class that stores application settings like API keys,
# database connection URLs, retry thresholds, and runtime environment names.
# An instance of Config is exported as 'config' for use across the entire application.

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """
    Application configuration class.
    
    Loads configuration settings from system environment variables
    with safe default fallback values for local development.
    """
    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
    NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///db/subrecover.db")
    MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", 4))
    MAX_DAYS = int(os.getenv("MAX_DAYS", 7))
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

config = Config()
