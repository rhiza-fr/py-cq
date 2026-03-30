FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

RUN apt-get update && apt-get install -y python3 python3-pip pv curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install asciinema --break-system-packages

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Pre-install cq (so the demo runs fast — we fake the install output)
RUN uv tool install python-code-quality

# Copy project and pre-warm all tool environments + cq diskcache
COPY dummy-project/ /root/demo-project/
RUN cd /root/demo-project && cq check . || true

# Fetch demo-magic
RUN curl -fsSL \
    https://raw.githubusercontent.com/paxtonhare/demo-magic/master/demo-magic.sh \
    -o /demo-magic.sh

COPY demo.sh /demo.sh
RUN chmod +x /demo.sh

WORKDIR /root
