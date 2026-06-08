FROM eclipse-temurin:17-jdk AS generate

ARG OBA_VERSION=3.6.1
ARG OPENAPI_GEN_VERSION=5.4.0

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /gen
RUN curl -sL "https://github.com/KnowledgeCaptureAndDiscovery/OBA/releases/download/${OBA_VERSION}/oba-${OBA_VERSION}-jar-with-dependencies.jar" -o oba.jar \
    && curl -sL "https://repo1.maven.org/maven2/org/openapitools/openapi-generator-cli/${OPENAPI_GEN_VERSION}/openapi-generator-cli-${OPENAPI_GEN_VERSION}.jar" -o openapi-generator-cli.jar

COPY config.yaml ontology.ttl ./
COPY custom ./custom

RUN java -jar oba.jar -c config.yaml

WORKDIR /gen/outputs/oba/servers/python
RUN cp ../openapi.yaml . \
    && java -jar /gen/openapi-generator-cli.jar generate \
        -i openapi.yaml -g python-flask -o server/ \
        --template-dir .openapi-generator/template \
        --ignore-file-override .openapi-generator-ignore \
    && cp -r .openapi-generator/template/static_files/settings/ server/openapi_server/settings/ \
    && cp -r .openapi-generator/template/static_files/utils/ server/openapi_server/utils/ \
    && cp .openapi-generator/template/static_files/user_controller.py server/openapi_server/controllers/ \
    && cp .openapi-generator/template/static_files/cached.py server/openapi_server/ \
    && mkdir -p server/contexts \
    && cp ../context.json ../context_class.json server/contexts/ \
    && cp -r ../../queries server/queries

FROM python:3.9-slim
WORKDIR /app
COPY --from=generate /gen/outputs/oba/servers/python/server/ /app/

RUN pip install --no-cache-dir -r requirements.txt "pyld==2.0.3"

EXPOSE 8080
CMD ["python", "-m", "openapi_server"]
