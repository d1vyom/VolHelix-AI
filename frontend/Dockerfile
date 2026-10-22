FROM node:22-alpine

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source code
COPY . .

# Next rewrites are compiled during build; browser URLs are compiled separately.
ARG BACKEND_URL=http://backend:8000
ARG NEXT_PUBLIC_SOCKET_URL=http://localhost:8000
ENV BACKEND_URL=$BACKEND_URL
ENV NEXT_PUBLIC_SOCKET_URL=$NEXT_PUBLIC_SOCKET_URL
RUN npm run build

# Expose port
EXPOSE 3000

# Start server
CMD ["npm", "start"]
