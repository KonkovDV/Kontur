FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG VITE_DEMO_BANNER=
ARG VITE_DEMO_TOKEN=
ENV VITE_DEMO_BANNER=$VITE_DEMO_BANNER
ENV VITE_DEMO_TOKEN=$VITE_DEMO_TOKEN
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY gateway/package.json gateway/package-lock.json ./
RUN npm ci --omit=dev
COPY gateway/src ./src
COPY --from=web /web/dist ./web

# Dependencies and application code remain owned by root and read-only at
# runtime. The fixed identity matches the compose runtime contract.
RUN addgroup -g 10001 app \
    && adduser -D -H -u 10001 -G app app

USER 10001:10001

EXPOSE 3000
CMD ["node", "src/server.js"]
