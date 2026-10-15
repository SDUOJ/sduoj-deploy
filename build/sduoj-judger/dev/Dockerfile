FROM registry.cn-beijing.aliyuncs.com/pre-sduoj/sduoj-judger@sha256:9f921b45954f641cd9b487d7f0be7f0c71506b23ca3eb673994e934434900d2e AS sandbox-build
USER root
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends libseccomp-dev
WORKDIR /src
RUN curl -fsSL https://codeload.github.com/SDUOJ/sduoj-sandbox/tar.gz/13ea99058b8cfccc131140b81f961989d7ac72dc \
    | tar -xz --strip-components=1
COPY arm64-seccomp.patch /tmp/arm64-seccomp.patch
RUN git apply /tmp/arm64-seccomp.patch && make -j4
COPY smoke.cpp smoke.in smoke.expected deny-network.c /tmp/
RUN g++ -O2 -static /tmp/smoke.cpp -o /tmp/smoke \
    && ./build/bin/sandbox --seccomp_rules=c_cpp --exe_path=/tmp/smoke \
       --input_path=/tmp/smoke.in --output_path=/tmp/smoke.out \
       --max_cpu_time=1000 --max_real_time=2000 | grep -q '"result":0' \
    && cmp /tmp/smoke.expected /tmp/smoke.out \
    && gcc -O2 -static /tmp/deny-network.c -o /tmp/deny-network \
    && ./build/bin/sandbox --seccomp_rules=c_cpp --exe_path=/tmp/deny-network \
       --input_path=/tmp/smoke.in --output_path=/tmp/deny-network.out \
       --max_cpu_time=1000 --max_real_time=2000 | grep -q '"signal":31'

FROM registry.cn-beijing.aliyuncs.com/pre-sduoj/sduoj-judger@sha256:9f921b45954f641cd9b487d7f0be7f0c71506b23ca3eb673994e934434900d2e
COPY --from=sandbox-build /src/build/bin/sandbox /opt/sduoj-sandbox/bin/sandbox
