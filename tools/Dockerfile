# Reproducible PS1 book environment.
#   docker build -f tools/Dockerfile -t ps1-book .
#   docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD":/book ps1-book bash
#   (inside)  tools/doctor.sh ;  parts/part-01-*/ch01-*/verify/verify.sh
# The toolchain lives in /opt/ps1-toolchain (not under /book) so mounting your
# checkout over /book does not hide it. PCSX-Redux runs headless (-cli); no GPU
# or display is required.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git curl ca-certificates \
        python3 python3-venv python3-pip xvfb \
        libgl1 libegl1 libx11-6 libxext6 \
        libfreetype6 libfontconfig1 libharfbuzz0b libfribidi0 \
    && rm -rf /var/lib/apt/lists/*

ENV PS1BOOK_TOOLCHAIN=/opt/ps1-toolchain \
    HOME=/tmp
WORKDIR /book

# Only tools/ is needed to install the toolchain (keeps the layer cacheable).
COPY tools /book/tools
RUN tools/setup.sh && chmod -R a+rX /opt/ps1-toolchain

ENV PATH=/opt/ps1-toolchain/bin:$PATH \
    PSN00BSDK_LIBS=/opt/ps1-toolchain/opt/psn00bsdk/lib/libpsn00b
CMD ["bash"]
