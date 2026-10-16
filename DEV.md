# Local development

The maintained guide is [OnlineJudge: local development](../OnlineJudge/website/docs/deployment/local-development.md).

Build server JAR/lib artifacts and publish the required MavenLocal modules before building judger. Start web2 and AutoLab using their own documented commands. `compose.dev.yaml` uses the repositories’ existing Dockerfiles and prebuilt judging-containers tools. It does not check out sibling source during Gradle/CI or apply sandbox patches.

Local state remains in ignored `data/`. Production deployment and database changes are separate operations.
