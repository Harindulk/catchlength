# Hugging Face Docker Space (CPU basic, free): serves the console and runs the agent on preloaded samples.
# Set MODEL_API_KEY as a Space secret; never bake it into the image.
FROM python:3.12-slim
RUN useradd -m app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY catchlength catchlength
COPY config config
COPY data/rules.json data/rules.json
COPY data/samples data/samples
COPY web web
RUN mkdir -p data/cache runs && chown -R app /app
USER app
ENV HOST=0.0.0.0 PORT=7860
EXPOSE 7860
CMD ["python", "-m", "catchlength.server"]
