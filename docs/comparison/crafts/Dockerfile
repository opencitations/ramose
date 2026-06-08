FROM node:18-bookworm-slim

ARG CRAFTS_COMMIT=f800304d0db1fb4674b2cf17978dba338717f6c1

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone https://github.com/guiveg/crafts.git . \
    && git checkout ${CRAFTS_COMMIT} \
    && npm install --omit=dev

# CRAFTS negotiates results with a non-standard "format" query parameter and no
# Accept header. The OpenCitations endpoints answer 406 to that and require
# standard Accept-based negotiation, so add the header to every SPARQL request.
RUN sed -i 's#\(options.method = endpoint.httpMethod == undefined? "GET" : endpoint.httpMethod;\)#\1\n\toptions.headers = { "Accept": "application/sparql-results+json" };#' js/sparqlClient.js

# CRAFTS validates its own responses against a strict schema that forbids extra
# top-level keys. The OpenCitations Index endpoint adds a non-standard "meta"
# member to its SPARQL JSON results, so disable the response self-validation.
RUN sed -i 's/validateResponses: true,/validateResponses: false,/' app.js

COPY config.js ./data/config.js
COPY data/users.json ./data/users.json
COPY apis/oc.json ./apis/oc.json

EXPOSE 8888
CMD ["node", "app.js"]
