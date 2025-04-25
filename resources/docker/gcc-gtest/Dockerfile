# Etapa de construcció
FROM gcc:latest AS builder

LABEL maintainer="Xavier Baró <https://github.com/xbaro>"

# Instal·la dependències per compilació i anàlisi
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        cmake \
        build-essential \
        ca-certificates \
        valgrind \
        ninja-build \
        python3 \
        python3-pip && \
    git clone --depth=1 https://github.com/google/googletest.git /tmp/googletest && \
    cd /tmp/googletest && \
    cmake -DCMAKE_CXX_STANDARD=20 -DCMAKE_CXX_STANDARD_REQUIRED=ON -DCMAKE_INSTALL_PREFIX=/usr/local . && \
    make -j"$(nproc)" && \
    make install && \
    rm -rf /tmp/googletest && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Etapa final (runtime)
FROM gcc:latest

# Copia les llibreries de Google Test i eines necessàries des de la build
COPY --from=builder /usr/local /usr/local

# Torna a instal·lar només les eines d'anàlisi i execució
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        cmake \
        build-essential \
        ca-certificates \
        valgrind \
        ninja-build \
        && apt-get clean && rm -rf /var/lib/apt/lists/*

# Defineix entorn per AddressSanitizer i suport C++20
ENV CXX="g++" \
    CC="gcc" \
    CXXFLAGS="-std=c++20 -g -fsanitize=address -fno-omit-frame-pointer" \
    LDFLAGS="-fsanitize=address"

WORKDIR /workspace

CMD ["/bin/bash"]
