FROM ubuntu:latest as pyra2yr

RUN dpkg --add-architecture i386

RUN \ 
	apt-get update -y && apt-get install -y \
	bash \
	python3 \
	python3-pip \
	wine32

# Create user and necessary folders
RUN useradd -m user && mkdir -p /home/user/project /home/user/.wine && chmod -R 0777 /home/user

RUN apt-get clean -y && \
	rm -rf /var/lib/apt/lists/*