FROM node:22-bookworm-slim
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG API_INTERNAL_URL=http://api:8000
ARG PUBLIC_FRAME_ANCESTOR=
ENV API_INTERNAL_URL=$API_INTERNAL_URL \
    PUBLIC_FRAME_ANCESTOR=$PUBLIC_FRAME_ANCESTOR
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
