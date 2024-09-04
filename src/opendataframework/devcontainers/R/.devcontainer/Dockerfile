ARG R_VERSION=3.12.4

FROM rocker/r-ver:${R_VERSION}

ARG DEBIAN_FRONTEND=noninteractive
ARG CRAN_MIRROR=https://cran.rstudio.com/

ENV TZ=UTC
ENV CRAN_MIRROR=$CRAN_MIRROR

RUN apt-get update -qqy && \
  apt-get install -y --no-install-recommends --no-install-suggests \
    libcairo2-dev \
    libxt-dev \
    libxml2-dev \
    libfreetype6-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libgs-dev \
    libpng-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

RUN install2.r languageserver httpgd \
    ggplot2 dplyr tidyr \
    && rm -rf /tmp/downloaded_packages

COPY .Rprofile /root/

RUN apt-get update -qq && apt-get -y install \
    python3-pip && \
    pip3 install radian

CMD ["radian"]
