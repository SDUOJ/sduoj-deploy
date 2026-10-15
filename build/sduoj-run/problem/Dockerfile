FROM sduoj-server:dev
COPY --from=problem-jar sduoj-problem-service-0.2.0-SNAPSHOT.jar /app/sduoj-problem-service-0.2.0-SNAPSHOT.jar
COPY --from=websocket-jar sduoj-websocket-0.2.0-SNAPSHOT.jar /app/sduoj-websocket-0.2.0-SNAPSHOT.jar
COPY --from=filesys-jar sduoj-filesys-service-0.2.0-SNAPSHOT.jar /app/sduoj-filesys-service-0.2.0-SNAPSHOT.jar
COPY --from=contest-jar sduoj-contest-service-0.2.0-SNAPSHOT.jar /app/sduoj-contest-service-0.2.0-SNAPSHOT.jar
COPY --from=user-jar sduoj-user-service-0.2.0-SNAPSHOT.jar /app/sduoj-user-service-0.2.0-SNAPSHOT.jar
