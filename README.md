# sduoj-deploy

Local Docker development: see [DEV.md](DEV.md). Run `./dev up`; start web2 and
Autolab manually. The legacy Compose file below is retained separately.

This project contains a Docker image meant to facilitate the deployment of [SDUOJ](https://github.com/SDUOJ/OnlineJudge).

## Project directory

- build: The source code of the docker image.
- env: Environment variable file for compose yaml.
- data: Some data files for running the service.

## How to scale

```bash
docker compose up -d --scale user-service=2
```

## Credits

* [nacos-docker](https://github.com/nacos-group/nacos-docker)
* [docker-compose-wait](https://github.com/ufoscout/docker-compose-wait)


## Online IDE 与评测机集成发布

ARM64/cgroup-v2统一Worker及评测沙箱加固的集成发布入口见 docs/COMBINED_RELEASE_20261026.md。旧IDE HTTP/v1八副本配置只保留历史用途；正式切换以本轮不可变镜像、配置与真实集成收据为准。
