# How this works:
# This configuration module loads environment variables from .env or streamlit secrets.
# It defines a Config class that stores application settings like API keys,
# database connection URLs, retry thresholds, and runtime environment names.
# An instance of Config is exported as 'config' for use across the entire application.

import os
from dotenv import load_dotenv

load_dotenv()

def _get_setting(key: str, default: str = None) -> str:
    """Retrieve setting from environment or streamlit secrets."""
    val = os.getenv(key)
    if val is not None and val != "":
        return val
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default

class Config:
    """
    Application configuration class.
    
    Loads configuration settings from system environment variables
    with safe default fallback values for local development and cloud hosting.
    """
    RAZORPAY_KEY_ID = _get_setting("RAZORPAY_KEY_ID", "rzp_test_placeholder")
    RAZORPAY_KEY_SECRET = _get_setting("RAZORPAY_KEY_SECRET", "secret_placeholder")
    NVIDIA_API_KEY = _get_setting("NVIDIA_API_KEY", "")
    NVIDIA_MODEL = _get_setting("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")
    DATABASE_URL = _get_setting("DATABASE_URL", "sqlite:///db/subrecover.db")
    MAX_ATTEMPTS = int(_get_setting("MAX_ATTEMPTS", "4"))
    MAX_DAYS = int(_get_setting("MAX_DAYS", "7"))
    ENVIRONMENT = _get_setting("ENVIRONMENT", "production")

config = Config()
