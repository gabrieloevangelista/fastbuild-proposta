FROM python:3.11-slim AS libredwg-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl -sL -o libredwg.tar.xz \
    https://github.com/LibreDWG/libredwg/releases/download/0.14/libredwg-0.14.tar.xz \
    && tar xf libredwg.tar.xz

WORKDIR /build/libredwg-0.14
RUN ./configure --prefix=/opt/libredwg \
        --disable-bindings --disable-static --disable-json --disable-docs \
    && make -j"$(nproc)" \
    && make install

# ---------------------------------------------------------------------------
FROM python:3.11-slim

COPY --from=libredwg-builder /opt/libredwg /opt/libredwg
ENV PATH="/opt/libredwg/bin:${PATH}"
ENV LD_LIBRARY_PATH="/opt/libredwg/lib:${LD_LIBRARY_PATH}"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
