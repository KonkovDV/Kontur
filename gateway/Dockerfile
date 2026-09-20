FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY src ./src

# Dependencies and application code remain owned by root and read-only at
# runtime. The fixed identity matches the compose runtime contract.
RUN addgroup -g 10001 app \
    && adduser -D -H -u 10001 -G app app

USER 10001:10001

EXPOSE 3000
CMD ["node", "src/server.js"]
