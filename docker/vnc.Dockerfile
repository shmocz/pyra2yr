FROM alpine:latest as src
RUN apk add --no-cache \
	bash \
	git \
	nodejs \
	openbox \
	python3 \
	terminus-font \
	tigervnc \
	xterm

RUN git clone "https://github.com/novnc/noVNC.git" --depth 1
RUN git clone "https://github.com/novnc/websockify" --depth 1 /noVNC/utils/websockify

RUN adduser -D user
USER user
WORKDIR /home/user
CMD sh -c "Xvnc :1 -depth 24 -geometry $RESOLUTION -br -rfbport=5901 -SecurityTypes None -AcceptSetDesktopSize=off & DISPLAY=1 openbox-session; fg"
