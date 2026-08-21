# SubRecover Agent

AI-powered subscription and recurring revenue recovery agent for Razorpay.

## Architecture
- **app/**: Configuration, database connection, ORM models, and utility helpers.
- **agent/**: LangGraph state, workflow graph, node execution, and recovery tools.
- **data/**: Synthetic transaction batch generation and sample failed datasets.
- **db/**: SQLite local storage for subscription states and recovery audits.
- **ui/**: Streamlit interactive recovery dashboard.

## Setup
1. Activate virtual environment: `venv\Scripts\activate`
2. Install requirements: `pip install -r requirements.txt`
3. Configure `.env` with your Razorpay test keys and NVIDIA API key.
4. Run agent: `python main.py`
5. Run dashboard: `streamlit run ui/streamlit_app.py`
