# Security Policy

## Threat Model & Design Principles

Praelector is a local-first desktop application designed to run entirely on the user's workstation. Its security architecture is guided by the following principles:

1. **Loopback-Only Binding (NF-01):** The engine sidecar binds exclusively to `127.0.0.1` on an OS-assigned ephemeral port (port `0`). It does not listen on external network interfaces.
2. **Bearer Token Authentication (D-10):** Tauri generates a 32-byte cryptographically secure random token and passes it to the engine via the environment (`PRAELECTOR_TOKEN`), never command-line arguments (which are readable in process listings). Every HTTP and WebSocket request requires an `Authorization: Bearer <token>` header.
3. **Origin Verification (D-10):** The engine verifies request headers and rejects any request whose `Origin` is present and not matching `{tauri://localhost, http://localhost:1420}`. This prevents malicious web pages running in a user's web browser from interacting with the local engine.
4. **Strict Content Security Policy (CSP):** The Tauri application configures a restrictive CSP permitting connections only to `'self'`, `http://127.0.0.1:*`, and `ws://127.0.0.1:*`.
5. **No Telemetry & No Tracking (NF-05):** Praelector contains zero telemetry, tracking pixels, or analytic phone-home beacons. Model weights and software dependencies are downloaded only upon explicit user request.
6. **No DRM Circumvention (EB-01, EB-02):** Praelector respects content protections. It explicitly refuses to open or process DRM-encrypted ebooks (`META-INF/encryption.xml` with encrypted content, `rights.xml`, `sinf.xml`). It does not provide mechanisms to strip DRM.
7. **No OCR (EB-04):** Praelector requires digital text layers. Scanned PDFs without extractable text layers are refused fail-closed.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| v1.x    | :white_check_mark: |
| < v1.0  | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in Praelector, please report it privately:

1. **GitHub Security Advisories (Preferred):** Open a draft advisory through the GitHub repository's "Security" tab.
2. **Email:** If you cannot use GitHub Advisories, email `czekanski.dominik@proton.me` with:
   - A clear description of the vulnerability and attack vector.
   - Proof of concept or reproduction steps.
   - Any proposed remediation if available.

We will acknowledge receipt of your report within 48 hours and work with you on a coordinated disclosure timeline. Please do not discuss or publish details until a patch has been released.
