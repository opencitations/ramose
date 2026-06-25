FROM node:24-bookworm-slim

ARG SHEXPOSE_COMMIT=3b69f07b4f8e814ee91fbd80de94b3aa480acf62
ARG SHEX2SPARQL_COMMIT=d9e7bc3ac11ad07c6e37ffec271a09b69bfe8831

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates python3 python3-venv python3-pip \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone https://github.com/chgoe/ShExpose-REST-API-Generation-from-Shapes.git . \
 && git checkout ${SHEXPOSE_COMMIT}

RUN npm install

RUN python3 -m venv venv && venv/bin/pip install --no-cache-dir linkml

RUN rm -rf resources/shapes/* config/config.yaml config/overwrite-mappings.yaml
COPY config/ ./config/
COPY resources/shapes/ ./resources/shapes/

RUN PATH="/app/node_modules/.bin:${PATH}" npx tsx src/prepareShex.ts

# The shex2sparql submodule's gitlink was never committed to ShExpose (only .gitmodules is present),
# so `git submodule update` fetches nothing; clone the engine explicitly at its pinned commit.
RUN git clone https://github.com/chgoe/neoShEx2SPARQL.git submodules/shex2sparql \
 && git -C submodules/shex2sparql checkout ${SHEX2SPARQL_COMMIT}

EXPOSE 3000
CMD ["npm", "start"]
