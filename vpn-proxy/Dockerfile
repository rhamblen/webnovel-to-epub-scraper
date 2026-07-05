# Minimal HTTP proxy, built from source rather than pulling a third-party image so
# there's nothing here beyond tinyproxy itself + our config.
FROM alpine:3.20
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
EXPOSE 8118
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
