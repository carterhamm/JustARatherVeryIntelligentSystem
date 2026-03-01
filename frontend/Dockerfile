# Build stage
FROM node:20-alpine as builder

WORKDIR /app

ARG VITE_API_URL=/api

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# Production stage
FROM nginx:alpine as production

# Install envsubst (part of gettext)
RUN apk add --no-cache gettext

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 80

# envsubst replaces ${BACKEND_URL} in the nginx template at startup
CMD ["/bin/sh", "-c", "envsubst '${BACKEND_URL}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
