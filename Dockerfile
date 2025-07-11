FROM python:3.11-slim

COPY . /workspace
WORKDIR /workspace
COPY requirements.txt ./

# Build tools (needed for numpy / FAISS)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        tesseract-ocr \
        tesseract-ocr-eng \
        && rm -rf /var/lib/apt/lists/* \
        && pip install --no-cache-dir -r requirements.txt


# Copy source, ui, and sample data
COPY src ./src
COPY app ./app
COPY data ./data

EXPOSE 8501

# Launch the Streamlit UI
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]