#!/usr/bin/env bash
cd "\$(dirname "\$0")"
source venv/bin/activate
exec streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0
