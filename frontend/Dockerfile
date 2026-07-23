# ScanToSheet frontend — build with Vite, serve static files with nginx.
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# API URL and key are injected at build time (Vite inlines VITE_* env vars).
# VITE_API_KEY is a 'user'-role key minted via /api/admin/keys — never the
# admin key — so the bundle only ever carries the least-privileged credential.
ARG VITE_API_URL=http://localhost:8000
ARG VITE_API_KEY=
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_API_KEY=$VITE_API_KEY
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
