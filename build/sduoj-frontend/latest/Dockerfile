FROM nginx

RUN apt-get update \
 && apt-get install -y wget unzip

RUN wget -O /manage.zip https://codeload.github.com/SDUOJ/sduoj-manage/zip/release \
 && wget -O /web.zip https://codeload.github.com/SDUOJ/sduoj-web/zip/release \
 && unzip -o -q -d / /manage.zip \
 && unzip -o -q -d / /web.zip \
 && rm /manage.zip \
 && rm /web.zip

EXPOSE 80

COPY nginx.conf /etc/nginx/nginx.conf