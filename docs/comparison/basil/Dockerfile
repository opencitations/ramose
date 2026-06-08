FROM maven:3-eclipse-temurin-17 AS build
RUN git clone --depth 1 --branch v1.0.0-RC1 https://github.com/basilapi/basil.git /src
WORKDIR /src
RUN mvn -B -DskipTests clean install

FROM eclipse-temurin:17-jre
WORKDIR /basil
COPY --from=build /src/server/target/basil-server-*.jar /basil/basil-server.jar
COPY --from=build /src/server/src/test/resources/log4j2.xml /basil/log4j2.xml
COPY basil-tdb2.ini /basil/basil-tdb2.ini

EXPOSE 8080
CMD ["java", "-jar", \
     "-Dbasil.configurationFile=/basil/basil-tdb2.ini", \
     "-Dlog4j.configurationFile=/basil/log4j2.xml", \
     "/basil/basil-server.jar", "-p", "8080"]
