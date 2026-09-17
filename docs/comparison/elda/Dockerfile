FROM maven:3-eclipse-temurin-21 AS build
RUN git clone --depth 1 --branch elda-3.0.4 https://github.com/epimorphics/elda.git /src
WORKDIR /src
RUN mvn -B -DskipTests clean install

FROM eclipse-temurin:21-jre
COPY --from=build /src/elda-standalone/target/elda-standalone-jar-with-dependencies.jar /opt/elda/elda.jar
COPY --from=build /src/elda-standalone/src/main/webapp/ /opt/elda/webapp/
COPY web.xml /opt/elda/webapp/WEB-INF/web.xml
COPY oc.ttl /opt/elda/webapp/specs/oc.ttl
COPY xslt/skg.xsl /opt/elda/webapp/xslt/skg.xsl
COPY meta-basic.auth /etc/elda/conf.d/ROOT/meta-basic.auth

ENV ELDA_WEBAPP_PATH=/opt/elda/webapp
ENV ELDA_CONTEXT_PATH=/

EXPOSE 8080
CMD ["java", "-jar", "/opt/elda/elda.jar"]
