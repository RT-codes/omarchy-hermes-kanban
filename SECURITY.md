# Security Policy

## Supported versions

Security fixes are provided for the latest release on the default branch.

## Reporting

Please report suspected vulnerabilities privately through GitHub Security Advisories for this repository. Do not include private keys, hostnames, task content, or other credentials in a public issue.

## Trust boundaries

This plugin is unsandboxed code running as the desktop user. Its trusted inputs are:

- The installed plugin commit
- The local Hermes executable selected by the user
- The user's OpenSSH configuration and known-hosts files
- The selected remote host and its Hermes installation

Hermes JSON and remote stderr are treated as untrusted data. Responses are size-bounded, parsed, normalized, allowlisted, and rendered as plain text. Raw stderr is not displayed.

The plugin does not protect against a compromised local user account, malicious OpenSSH configuration already trusted by the user, or a compromised Hermes executable. It deliberately does not install keys, accept unknown host keys, store credentials, elevate privileges, or enable SSH agent forwarding.

## Data handling

Board selection is the only plugin state written to disk. Task snapshots remain in memory. Task bodies are disabled by default. Remote mode transfers sanitized board metadata and selected active-task details over the established SSH channel.
