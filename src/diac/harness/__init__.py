"""Black-box evaluation harness for RQ2 experiments (E3, E4, E6).

Components:
  raw.RawDokploy      - read-only HTTP client for Dokploy; the independent oracle's only data source
  proxy.CallRecorder  - reverse proxy between the CLI and Dokploy that logs every call (O-traffic)
  cli.DokployCli      - runs the SUT CLI as a subprocess and parses exit codes
  oracle              - handwritten expected-state checks per kind, written without reading SUT code
  scenarios           - loads scenario YAML files (experiments/e3_convergence/scenarios/)
"""
