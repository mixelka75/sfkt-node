FROM debian:12-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    ca-certificates \
    python3 \
    python3-pip \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Install Xray-core (latest version with REALITY support)
ARG XRAY_VERSION=25.9.11
RUN curl -L https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip -o /tmp/xray.zip \
    && unzip /tmp/xray.zip -d /usr/local/bin/ \
    && rm /tmp/xray.zip \
    && chmod +x /usr/local/bin/xray

# Create directories
RUN mkdir -p /etc/xray \
    /var/log/xray \
    /usr/local/share/xray

# Copy config template
COPY config/xray_template.json /etc/xray/config.json

# Copy scripts
COPY scripts/ /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh /usr/local/bin/entrypoint.sh

# Install Python dependencies for node agent
# Using --break-system-packages is safe in Docker containers (isolated environment)
RUN pip3 install --no-cache-dir --break-system-packages \
    requests \
    aiohttp \
    psutil

# Copy node agent
COPY node_agent.py /usr/local/bin/node_agent.py
RUN chmod +x /usr/local/bin/node_agent.py

# Copy supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports
EXPOSE 443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:10085/stats || exit 1

# Use entrypoint script
CMD ["/usr/local/bin/entrypoint.sh"]
