FROM eclipse-temurin:21-jre

ARG FUSEKI_VERSION=6.2.0
ARG FUSEKI_SHA512=ba65f5867d2d4741b2ed9e2af5a0d4fbb447909894ab2a0c6bc4dac8997f4fe339c87b13c48d45d054977769f0f8bf763ea346b1f7792d5cdc458041bd43a132

RUN curl -fsSL "https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-${FUSEKI_VERSION}.tar.gz" -o /tmp/fuseki.tar.gz \
 && echo "${FUSEKI_SHA512}  /tmp/fuseki.tar.gz" | sha512sum -c - \
 && tar -xzf /tmp/fuseki.tar.gz -C /opt \
 && mv "/opt/apache-jena-fuseki-${FUSEKI_VERSION}" /opt/fuseki \
 && rm /tmp/fuseki.tar.gz

WORKDIR /opt/fuseki
EXPOSE 3030
ENTRYPOINT ["/opt/fuseki/fuseki-server"]
