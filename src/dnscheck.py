"""DNS leak detection: find out which resolver the outside world sees.

A fingerprint browser is only as private as its DNS path. mihomo's fake-ip
mode answers A/AAAA queries locally, but every other record type (TXT, MX,
CNAME, ...) is forwarded to the configured upstream resolvers. If those
upstreams sit on the local network, the recursive resolver attaches an EDNS
Client Subnet with the real home subnet, and any leak-test site can read it.

The probe below asks a TXT record that echoes back what the authoritative
server observed: Google's ``o-o.myaddr.l.google.com`` returns the resolver
address and, when the resolver sends one, the client subnet it attached.
"""

from __future__ import annotations

import re
import socket
import struct
from dataclasses import dataclass

# Google's diagnostic TXT record. It answers with the address of the
# resolver that queried Google, plus the EDNS client subnet, if any.
PROBE_NAME = "o-o.myaddr.l.google.com"
PROBE_SERVER = "198.18.0.2"

# Ranges that public resolvers use, so a remote lookup can be told apart from
# one handled by the local network. Cloudflare's 1.1.1.1 answers from 1.1.1.1
# and 2400:cb00::/32, Google from 8.8.8.8, Quad9 from 9.9.9.9.
PROXY_RESOLVER_HINTS = (
    "1.1.1.1",
    "1.0.0.1",
    "8.8.8.8",
    "8.8.4.4",
    "9.9.9.9",
    "104.16.",
    "2400:cb00",
    "2606:4700",
    "2001:4860",
    "2620:fe",
)


@dataclass(frozen=True)
class DnsResult:
    """What the authoritative server saw for our probe query."""

    resolver: str | None
    client_subnet: str | None
    raw: str

    @property
    def leaked(self) -> bool:
        """True when the resolver disclosed a client subnet (a real leak)."""
        return self.client_subnet is not None

    @property
    def resolved_remotely(self) -> bool:
        """True when the resolver looks like a public one rather than a local ISP."""
        if self.resolver is None:
            return False
        return any(hint in self.resolver for hint in PROXY_RESOLVER_HINTS)


def _encode_query(name: str, qtype: int = 16) -> bytes:
    """Build a DNS query packet for `name` (qtype 16 is TXT)."""
    header = struct.pack(">HHHHHH", 0x4D42, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(part)]) + part.encode() for part in name.split(".")) + b"\x00"
    return header + qname + struct.pack(">HH", qtype, 1)


def _skip_name(data: bytes, offset: int) -> int:
    """Return the offset just past a (possibly compressed) domain name."""
    while offset < len(data):
        length = data[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + length
    return offset


def _parse_txt(data: bytes) -> list[str]:
    """Pull the TXT strings out of a DNS response."""
    if len(data) < 12:
        return []
    qdcount, ancount = struct.unpack(">HH", data[4:8])
    offset = 12
    for _ in range(qdcount):
        offset = _skip_name(data, offset) + 4
    values: list[str] = []
    for _ in range(ancount):
        offset = _skip_name(data, offset)
        if offset + 10 > len(data):
            break
        rtype, _rclass, _ttl, rdlength = struct.unpack(">HHIH", data[offset : offset + 10])
        offset += 10
        rdata = data[offset : offset + rdlength]
        offset += rdlength
        if rtype != 16:
            continue
        index = 0
        while index < len(rdata):
            size = rdata[index]
            values.append(rdata[index + 1 : index + 1 + size].decode("utf-8", "replace"))
            index += 1 + size
    return values


def query_probe(server: str = PROBE_SERVER, name: str = PROBE_NAME, timeout: float = 5.0) -> DnsResult:
    """Query the probe record and report what the authoritative server saw."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(_encode_query(name), (server, 53))
            data, _ = sock.recvfrom(4096)
    except (OSError, socket.timeout) as exc:
        return DnsResult(None, None, f"query failed: {exc}")

    values = _parse_txt(data)
    raw = " | ".join(values)
    client_subnet = None
    resolver = None
    for value in values:
        match = re.search(r"edns0-client-subnet\s+([0-9.]+/\d+)", value)
        if match:
            client_subnet = match.group(1)
    # The bare address in the response is the resolver that reached Google.
    for value in values:
        if re.fullmatch(r"[0-9a-fA-F.:]+", value) and ("." in value or ":" in value):
            resolver = value
            break
    return DnsResult(resolver, client_subnet, raw)


def describe(result: DnsResult) -> str:
    """A one-line summary for the console."""
    if result.resolver is None and "failed" in result.raw:
        return f"DNS probe failed: {result.raw}"
    parts = [f"resolver {result.resolver or 'unknown'}"]
    if result.client_subnet:
        parts.append(f"client subnet {result.client_subnet} (LEAK)")
    else:
        parts.append("no client subnet")
    return ", ".join(parts)
