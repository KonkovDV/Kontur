FROM node:25-alpine@sha256:bdf2cca6fe3dabd014ea60163eca3f0f7015fbd5c7ee1b0e9ccb4ced6eb02ef4 AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG VITE_DEMO_BANNER=
ARG VITE_DEMO_TOKEN=
ENV VITE_DEMO_BANNER=$VITE_DEMO_BANNER
ENV VITE_DEMO_TOKEN=$VITE_DEMO_TOKEN
RUN npm run build

FROM node:25-alpine@sha256:bdf2cca6fe3dabd014ea60163eca3f0f7015fbd5c7ee1b0e9ccb4ced6eb02ef4
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
