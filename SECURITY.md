# Security Policy

## Supported versions

Until the first stable release, only the latest published Community version is
supported. Security and data-integrity fixes may be released outside the normal
low-frequency release schedule.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, event media,
network topology or personal data. Report vulnerabilities privately by email to
**nanexus.ai@gmail.com**. Use a clear subject such as `[SECURITY] Vulnerability
report` and include the affected version, reproduction steps, potential impact
and any suggested mitigation. Do not attach real credentials, camera media or
other personal data; use redacted samples where possible.

After the public repository is created, GitHub Private Vulnerability Reporting
should be enabled as the preferred reporting channel. The email address above
will remain the fallback security contact.

The v0.1.0 Community UI and API provide no built-in authentication or
authorization. Deploy them only on a trusted local network and do not expose
ports 5173 or 8000 directly to the public Internet. Authentication and
public-network deployment are outside the scope of this release.
