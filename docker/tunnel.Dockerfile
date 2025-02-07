FROM alpine:latest

RUN apk add --update --no-cache python3 git
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools
RUN python3 -m pip install 'pycncnettunnel @ git+https://github.com/shmocz/pycncnettunnel.git'
RUN adduser -D user
USER user

CMD pycncnettunnel
