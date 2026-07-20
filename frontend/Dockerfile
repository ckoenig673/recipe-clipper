FROM nginx:alpine

ARG CACHE_BUST_VERSION=dev

COPY . /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN find /usr/share/nginx/html -maxdepth 1 -type f \( -name 'index.html' -o -name 'service-worker.js' \) -exec   sed -i "s/__CACHE_BUST_VERSION__/${CACHE_BUST_VERSION}/g" {} +
