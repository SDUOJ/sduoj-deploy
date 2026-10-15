FROM eclipse-temurin:17-jdk AS worker-build
WORKDIR /src/sduoj-judger
COPY --from=judger-src . .
COPY --from=server-src . /src/sduoj-server-private
RUN --mount=type=cache,target=/root/.gradle \
    sh ./gradlew --no-daemon --max-workers=4 \
      -Dorg.gradle.jvmargs="-Xmx2048m -XX:MaxMetaspaceSize=768m" :sduoj-judger-service:bootJar

FROM sduoj-judger:dev AS sandbox-build
USER root
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libseccomp-dev
WORKDIR /src
COPY --from=sandbox-src . .
COPY arm64-seccomp.patch /tmp/arm64-seccomp.patch
RUN git apply /tmp/arm64-seccomp.patch && make -j4
# Test separate streams and backwards-compatible combined output at image build time.
RUN printf '#include <stdio.h>\nint main(){puts("out");fputs("err\\n",stderr);return 0;}\n' > /tmp/streams.c \
    && gcc -static /tmp/streams.c -o /tmp/streams \
    && ./build/bin/sandbox --exe_path=/tmp/streams --output_path=/tmp/stdout --error_path=/tmp/stderr --max_real_time=2000 | grep -q '\"result\":0' \
    && test "$(cat /tmp/stdout)" = out && test "$(cat /tmp/stderr)" = err \
    && ./build/bin/sandbox --exe_path=/tmp/streams --output_path=/tmp/combined --max_real_time=2000 | grep -q '\"result\":0' \
    && grep -q out /tmp/combined && grep -q err /tmp/combined
FROM sduoj-judger:dev
COPY --from=sandbox-build /src/build/bin/sandbox /opt/sduoj-sandbox/bin/sandbox
COPY --from=worker-build /src/sduoj-judger/sduoj-judger-service/build/libs/sduoj-judger.jar /app/sduoj-judger.jar
