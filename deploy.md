## Reference
https://medium.com/@gary.ascuy/docker-free-ssl-tls-certs-lets-encrypt-184e62ab272e

## Local server setup

```shell
curl -fsSL https://get.docker.com | sh
```
```shell
sudo apt install git
```

```shell
git clone https://github.com/BenjaminPelletier/aerodata
```

```shell
cd aerodata
```

```shell
sudo ./run.sh
```

## nginx setup

```shell
sudo docker run --rm -p 80:80 -p 443:443 \
    -v /root/nginx/letsencrypt:/etc/letsencrypt \
    certbot/certbot certonly -d aerodata.uastech.co \
    --standalone -m pelletierb@wing.com --agree-tos
```

```shell
sudo openssl dhparam -out /root/nginx/dhparam.pem 4096
```

### /root/nginx/nginx.conf

```
events {
    worker_connections  4096;
}

http {
  server {
    listen 80;
    server_name aerodata.uastech.co;
    return 301 https://$host$request_uri;
  }

  server {
    listen 443 ssl default deferred;
    server_name aerodata.uastech.co;

    ssl_certificate      /etc/letsencrypt/live/aerodata.uastech.co/fullchain.pem;
    ssl_certificate_key  /etc/letsencrypt/live/aerodata.uastech.co/privkey.pem;
    ssl_dhparam /etc/ssl/certs/dhparam.pem;
    add_header Strict-Transport-Security "max-age=63072000; includeSubdomains";  
    ssl_trusted_certificate /etc/letsencrypt/live/aerodata.uastech.co/fullchain.pem;

    location / {
      proxy_pass http://host.docker.internal:8090;
    }
  }
}
```

```shell
sudo docker run --restart always -d -p 80:80 -p 443:443 \
    -v /root/nginx/letsencrypt:/etc/letsencrypt \
    -v /root/nginx/dhparam.pem:/etc/ssl/certs/dhparam.pem \
    -v /root/nginx/nginx.conf:/etc/nginx/nginx.conf \
    --add-host=host.docker.internal:host-gateway \
    --name proxy \
    nginx:alpine
```

## Cert renewal

```shell
docker stop proxy
```

```shell
docker run --rm -p 80:80 -p 443:443 \
  -v /root/nginx/letsencrypt:/etc/letsencrypt \
  certbot/certbot renew
```

```shell
docker start proxy
```
