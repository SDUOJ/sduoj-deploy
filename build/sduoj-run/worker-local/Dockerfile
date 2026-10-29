# The standard dev Dockerfile still compiles source and verifies the sandbox.
# This local overlay reuses that verified sandbox with the latest host-built JAR.
FROM sduoj-run-worker:dev
COPY --from=worker-jar sduoj-judger.jar /app/sduoj-judger.jar
