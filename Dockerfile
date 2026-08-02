# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Set python environmental variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1


# Copy the server directory (including python scripts and static web assets)
COPY server/ /app/server/

# Install minimal third-party dependencies required by the server (excludes client libraries)
RUN pip install --no-cache-dir -r server/server_requirements.txt

# Create volume mountpoints for persistent configurations & custom word lists
# Users can mount a directory containing config.json and words.json to preserve lobby states
VOLUME ["/app/server"]

# Expose the server game port (WebSockets & HTTP static file serving)
EXPOSE 8765

# Start the game server
CMD ["python", "server/server.py"]
