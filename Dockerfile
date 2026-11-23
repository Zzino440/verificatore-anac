FROM eclipse-temurin:21-jdk-alpine AS build
WORKDIR /src
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN ./mvnw -q dependency:go-offline
COPY src/main/java src/main/java
COPY src/main/resources src/main/resources
RUN ./mvnw -q -DskipTests package

FROM eclipse-temurin:21-jre-alpine
RUN apk add --no-cache python3 tzdata && adduser -D -u 1000 verifica && mkdir /dati && chown verifica /dati
COPY src/main/python/verifica_gara /app/script/verifica_gara
COPY --from=build /src/target/verifica-servizio-*.jar /app/servizio.jar
ENV SCRIPT_DIR=/app/script DATI_DIR=/dati PYTHON=python3 TZ=Europe/Rome
USER verifica
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/servizio.jar"]
