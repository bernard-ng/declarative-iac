"""Analysis and evaluation harness for the declarative-IaC-over-RPC study.

The harness deliberately does not import or link any dokploy-iac crate: it reads the
system under study (SUT) through git at a pinned commit, runs its CLI as a black box,
and observes Dokploy through raw HTTP. That keeps oracles independent of engine bugs.
"""
