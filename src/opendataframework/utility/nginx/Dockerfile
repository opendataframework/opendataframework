FROM nginx
COPY ./utility/nginx/nginx.conf /etc/nginx/conf.d/default.conf

RUN rm -rf /usr/share/nginx/html/*
COPY ./utility/nginx/static/ /usr/share/nginx/html/
