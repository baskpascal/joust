"""Answer "why can't I reach this host?" without ever touching a secret.

An agent that hits an unreachable competition URL needs *some* way to find
out why — but the honest answer to "is DNS resolving, does the TLS handshake
complete, does the certificate validate, what HTTP status comes back" never
requires reading a credential file, an environment variable, or a private
key. This module is that honest, narrow answer: a direct library call with
no shell, no filesystem access outside the trust store Python already reads
for any HTTPS connection, and nothing it returns can contain a secret because
nothing it does can read one.

This exists so that a diagnosis never *needs* to reach for a shell command in
the first place — the safer path is also the easier one to reach for.
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass
class NetworkDiagnosticResult:
    target: str
    host: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    dns_resolved: bool = False
    resolved_addresses: list[str] = field(default_factory=list)
    dns_error: str | None = None
    tcp_connected: bool = False
    tcp_error: str | None = None
    tls_handshake_ok: bool | None = None
    tls_error: str | None = None
    certificate_valid: bool | None = None
    certificate_subject: str | None = None
    certificate_issuer: str | None = None
    certificate_not_after: str | None = None
    http_status: int | None = None
    http_error: str | None = None
    reachable: bool = False
    summary: str = ""

    def to_evidence_text(self) -> str:
        """A plain-language account of what was actually checked and found.

        This, not the raw checks, is what an approval prompt or a chat
        message should show: no host implementation detail a non-technical
        user would need to interpret.
        """

        lines = [self.summary]
        if self.dns_error:
            lines.append(f"DNS: {self.dns_error}")
        elif self.resolved_addresses:
            lines.append(f"DNS: resolved to {', '.join(self.resolved_addresses[:3])}")
        if self.tcp_error:
            lines.append(f"Connection: {self.tcp_error}")
        if self.tls_error:
            lines.append(f"TLS: {self.tls_error}")
        elif self.tls_handshake_ok:
            cert_state = "valid" if self.certificate_valid else "could not be validated"
            lines.append(f"TLS: handshake succeeded, certificate {cert_state}")
        if self.http_status is not None:
            lines.append(f"HTTP: responded with status {self.http_status}")
        elif self.http_error:
            lines.append(f"HTTP: {self.http_error}")
        return "\n".join(lines)


def diagnose(
    target: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
) -> NetworkDiagnosticResult:
    """Run every check this module supports against one target and stop.

    `target` is a URL or a bare hostname; either is accepted so a caller
    does not have to construct a URL just to check a domain. No credential,
    environment variable, or file outside the process's normal TLS trust
    store is ever read — the CA bundle Python's own `ssl` module already
    uses for any HTTPS request, not a path the caller names.
    """

    parsed = urlparse(target if "://" in target else f"https://{target}")
    host = parsed.hostname or target
    result = NetworkDiagnosticResult(target=target, host=host)

    try:
        addresses = sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
        result.dns_resolved = True
        result.resolved_addresses = addresses
    except OSError as error:
        result.dns_error = str(error)
        result.summary = (
            f"Could not resolve {host}: the domain does not appear to exist or DNS is unreachable."
        )
        return result

    port = parsed.port or (443 if parsed.scheme != "http" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            result.tcp_connected = True
    except OSError as error:
        result.tcp_error = str(error)
        result.summary = f"{host} resolved, but nothing answered on port {port}."
        return result

    if parsed.scheme != "http":
        context = ssl.create_default_context()
        try:
            with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
                with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                    result.tls_handshake_ok = True
                    result.certificate_valid = True
                    cert = tls_sock.getpeercert()
                    if cert:
                        result.certificate_subject = _cert_name(cert.get("subject"))
                        result.certificate_issuer = _cert_name(cert.get("issuer"))
                        result.certificate_not_after = cert.get("notAfter")
        except ssl.SSLCertVerificationError as error:
            result.tls_handshake_ok = True
            result.certificate_valid = False
            result.tls_error = f"certificate did not validate: {error.verify_message}"
        except (ssl.SSLError, OSError) as error:
            result.tls_handshake_ok = False
            result.tls_error = str(error)
            result.summary = f"{host} accepted the connection, but the secure handshake failed."
            return result

    request = Request(target if "://" in target else f"https://{target}", method="HEAD")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            result.http_status = response.status
    except HTTPError as error:
        # A real HTTP response, even an error one, proves the host is
        # reachable and serving something — a 403 or a 404 is not "down".
        result.http_status = error.code
    except URLError as error:
        result.http_error = str(error.reason)

    result.reachable = result.http_status is not None
    if result.reachable:
        result.summary = f"{host} is reachable (HTTP {result.http_status})."
    elif result.tls_error:
        pass  # summary already set above
    else:
        result.summary = f"{host} accepted a connection but did not answer an HTTP request."
    return result


def _cert_name(name_tuples: object) -> str | None:
    if not name_tuples:
        return None
    parts = []
    for rdn in name_tuples:  # type: ignore[assignment]
        for key, value in rdn:
            parts.append(f"{key}={value}")
    return ", ".join(parts) or None


__all__ = ["NetworkDiagnosticResult", "diagnose"]
