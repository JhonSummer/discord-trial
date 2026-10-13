"""Perceptual quality harness for Lyra voice over the BLE mesh model.

Encodes clean speech with Lyra v2 at 3.2 / 6 / 9.2 kbps, drops frames the mesh
simulator marks lost (residual error, congestion, or jitter-buffer late loss,
including multi-hop paths), and scores the concealed audio with ViSQOL, DNSMOS
P.835, and STOI.
"""
