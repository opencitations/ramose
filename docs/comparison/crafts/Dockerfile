FROM node:22-bookworm-slim

ARG CRAFTS_COMMIT=30b8d69de803bc33853795c2b68af44d15fe4096

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone https://github.com/guiveg/crafts.git . \
    && git checkout ${CRAFTS_COMMIT} \
    && npm install --omit=dev

COPY config.js ./data/config.js
COPY data/users.json ./data/users.json
COPY apis/oc.json ./apis/oc.json

EXPOSE 8888
CMD ["node", "app.js"]
