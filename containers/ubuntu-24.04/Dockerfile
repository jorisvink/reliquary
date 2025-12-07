FROM ubuntu:24.04

RUN apt update && apt -y upgrade

RUN apt -y install \
	build-essential \
	make \
	git \
	clang \
	python3-dev \
	libcurl4-openssl-dev \
	libpq-dev \
	pkg-config

WORKDIR /home/builder
