# Joust is a Plow Hermes variant. Generic runtime behavior stays in the
# immutable upstream base; this image owns only its persona, skills, mission
# package, and supervised Agent Index reporter.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-8710797b6409c77df560c6198407765d138ea617@sha256:b9627febe57e34ec0df373709ad91a27a7fda68093e76d519678cac1012614f9

# GitHub is part of Joust's execution/observation plane. Keep the package
# version explicit so a rebuild cannot silently change the CLI contract.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gh=2.46.0-3 \
 && rm -rf /var/lib/apt/lists/*

COPY --chmod=0644 runtime/persona.md /opt/hermes/plow-seed/persona.md
COPY --chmod=0644 LICENSE NOTICE /usr/share/doc/joust/

COPY --chmod=0644 pyproject.toml LICENSE README.md compose.yml Dockerfile /opt/joust/
COPY hackathon_competitor/ /opt/joust/hackathon_competitor/
RUN find /opt/joust -type d -exec chmod 0755 {} + \
 && find /opt/joust -type f -exec chmod 0644 {} +
# plow-init deliberately leaves the root-owned shared home traversable and
# writable by the hermes group. Hermes CLI commands call _secure_dir(), so
# carry that contract into every subprocess instead of letting a root-run
# diagnostic silently revert the volume to 0700 root:root/root:hermes.
ENV PYTHONPATH=/opt/joust \
    HERMES_HOME_MODE=3770 \
    GH_CONFIG_DIR=/var/lib/hermes/.config/gh

COPY skills/ /opt/hermes/skills/
RUN find /opt/hermes/skills -mindepth 1 -type d -exec chmod 0755 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f -exec chmod 0644 {} +

# The Agent Index client is owned upstream. Fetch exactly the reviewed commit
# and verify its bytes before it can enter this credential-bearing image.
COPY vendor/client.pin /opt/plow/agent-index-client.pin
RUN set -eu; \
    sha="$(sed -n 's/^sha=//p' /opt/plow/agent-index-client.pin)"; \
    want="$(sed -n 's/^sha256=//p' /opt/plow/agent-index-client.pin)"; \
    path="$(sed -n 's/^path=//p' /opt/plow/agent-index-client.pin)"; \
    curl -fsS --max-time 60 -o /opt/plow/agent-index-client.py \
      "https://raw.githubusercontent.com/plow-pbc/agent-index-client/${sha}/${path}"; \
    got="$(sha256sum /opt/plow/agent-index-client.py | cut -d' ' -f1)"; \
    [ "$got" = "$want" ] || { echo "agent-index client is $got, pin says $want" >&2; exit 1; }; \
    chmod 0644 /opt/plow/agent-index-client.py

COPY image/s6-overlay/ /etc/s6-overlay/
RUN chmod 0755 /etc/s6-overlay/s6-rc.d/agent-index/run
RUN install -d -o 10000 -g 10000 -m 0700 /var/lib/hermes/hackathon_competitor
