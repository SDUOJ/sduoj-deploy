FROM nacos/nacos-server:v2.1.2-slim

# download docker-compose-wait
COPY --from=sduoj/docker-compose-wait:latest /wait /wait

ENTRYPOINT /wait \
 && bin/docker-startup.sh
