# How this works:
# Main entry point for the SubRecover Agent CLI application.
# Imports configuration and handles initial pipeline execution.

def main():
    """
    Main application entry function.
    
    Initializes configuration and prints startup information.
    """
    from app.config import config
    print(f"SubRecover Agent initialized in {config.ENVIRONMENT} mode.")

if __name__ == "__main__":
    main()
