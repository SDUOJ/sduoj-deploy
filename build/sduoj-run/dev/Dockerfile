FROM eclipse-temurin:17-jdk AS worker-build
WORKDIR /src/sduoj-judger
COPY --from=judger-src . .
COPY --from=server-src . /src/sduoj-server-private
RUN --mount=type=cache,target=/root/.gradle \
    sh ./gradlew --no-daemon --max-workers=4 \
      -Dorg.gradle.jvmargs="-Xmx2048m -XX:MaxMetaspaceSize=768m" :sduoj-judger-service:bootJar

FROM ubuntu:22.04 AS sandbox-build
USER root
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends build-essential libseccomp-dev
WORKDIR /src
COPY --from=sandbox-src . .
RUN make -B -j4 && ./build/bin/sandbox --version
# Namespace tests run with CAP_SYS_ADMIN after building the image; BuildKit
# RUN steps do not provide that runtime capability.


FROM sduoj-judger:dev
COPY --from=sandbox-build /src/build/bin/sandbox /opt/sduoj-sandbox/bin/sandbox
COPY --from=worker-build /src/sduoj-judger/sduoj-judger-service/build/libs/sduoj-judger.jar /app/sduoj-judger.jar
COPY --from=sandbox-src docker/judge-entrypoint.sh /usr/local/bin/sduoj-judge-entrypoint
RUN chmod 0755 /usr/local/bin/sduoj-judge-entrypoint
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/sduoj-judge-entrypoint"]
