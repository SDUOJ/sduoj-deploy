FROM alpine AS downloader

RUN wget -O /manage.zip https://codeload.github.com/SDUOJ/sduoj-manage/zip/stable-release \
 && wget -O /web.zip    https://codeload.github.com/SDUOJ/sduoj-web/zip/stable-release \
 && unzip -o -q -d / /manage.zip \
 && unzip -o -q -d / /web.zip \
 && mv /sduoj-web* /sduoj-web \
 && mv /sduoj-manage* /sduoj-manage

FROM nginx

COPY --from=downloader /sduoj-web /sduoj-web
COPY --from=downloader /sduoj-manage /sduoj-manage

EXPOSE 80
