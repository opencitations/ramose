FROM maven:3-eclipse-temurin-21 AS build
RUN git clone --depth 1 --branch elda-3.0.0 https://github.com/epimorphics/elda.git /src
WORKDIR /src
RUN mvn -B -DskipTests clean install

FROM tomcat:11-jre21-temurin
RUN rm -rf /usr/local/tomcat/webapps/*
COPY --from=build /src/elda-standalone/target/elda-standalone/ /usr/local/tomcat/webapps/ROOT/
COPY web.xml /usr/local/tomcat/webapps/ROOT/WEB-INF/web.xml
COPY oc.ttl /usr/local/tomcat/webapps/ROOT/specs/oc.ttl
COPY xslt/skg.xsl /usr/local/tomcat/webapps/ROOT/xslt/skg.xsl

EXPOSE 8080
CMD ["catalina.sh", "run"]
