"""Utility modules for the late-rollcall protocol runner.

`main.py` stays a thin orchestrator; this package holds the reusable pieces:

- config: paths, JSON loading, validation, URL helpers, the enabled switch
- net: HTTP transport, ``${dotted.path}`` header interpolation, response unwrap
- crypto: AES-128-CBC query-param encryption
- schedule: sign-in time-window and late-flag logic
- protocol: read-only init / server-timestamp fetches and status introspection
- payload: campus / location / check & clockIn request-payload builders
"""
