# sduoj-deploy

This project contains a Docker image meant to facilitate the deployment of [SDUOJ](https://github.com/SDUOJ/OnlineJudge).

## Project directory

- build: The source code of the docker image.
- env: Environment variable file for compose yaml.
- example: Docker compose example for SDUOJ.

## How to scale

```bash
docker-compose -f pseudo-distributed-ip.yaml up -d --scale user-service=2
```

## Credits

* [nacos-docker](https://github.com/nacos-group/nacos-docker)
* [docker-compose-wait](https://github.com/ufoscout/docker-compose-wait)

