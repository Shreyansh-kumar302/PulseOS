# Stage 1: Build React Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python Runner
FROM python:3.11-slim
WORKDIR /app

# Install Python requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy compiled frontend assets into the expected server path
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Copy backend files
COPY backend /app/backend

# Configure container runtime variables
EXPOSE 5000
ENV PORT=5000
ENV PYTHONUNBUFFERED=1

# Start the uvicorn server dynamically on the allocated port
CMD ["python", "backend/app.py"]
