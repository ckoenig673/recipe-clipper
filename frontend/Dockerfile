FROM nginx:1.31.8-alpine@sha256:713fc2ebfd92e8217db451477182ee91944b123d2b1ee9fd5a8c6e91ca6c3a11

ARG CACHE_BUST_VERSION=dev

COPY . /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN find /usr/share/nginx/html -maxdepth 1 -type f \( -name 'index.html' -o -name 'service-worker.js' \) -exec   sed -i "s/__CACHE_BUST_VERSION__/${CACHE_BUST_VERSION}/g" {} +
