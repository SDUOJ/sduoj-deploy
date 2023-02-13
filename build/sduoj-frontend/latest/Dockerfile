FROM nginx

RUN apt-get update \
 && apt-get install -y wget unzip

RUN wget -O /manage.zip https://codeload.github.com/SDUOJ/sduoj-manage/zip/stable-release \
 && wget -O /web.zip    https://codeload.github.com/SDUOJ/sduoj-web/zip/stable-release \
 && unzip -o -q -d / /manage.zip \
 && unzip -o -q -d / /web.zip \
 && mv /sduoj-web* /sduoj-web \
 && mv /sduoj-manage* /sduoj-manage \
 && rm /manage.zip \
 && rm /web.zip

EXPOSE 80