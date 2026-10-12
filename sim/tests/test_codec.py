import pytest

from meshvoice.codec import (
    LYRA_V2_3200, LYRA_V2_6000, LYRA_V2_9200, CodecProfile, by_name,
)


def test_payload_bytes_match_bitrate_at_20ms():
    assert LYRA_V2_3200.payload_bytes == pytest.approx(8.0)
    assert LYRA_V2_6000.payload_bytes == pytest.approx(15.0)
    assert LYRA_V2_9200.payload_bytes == pytest.approx(23.0)


def test_frames_per_second():
    assert LYRA_V2_9200.frames_per_second == pytest.approx(50.0)
    assert LYRA_V2_9200.frame_seconds == pytest.approx(0.02)


def test_packet_bits_no_overhead():
    assert LYRA_V2_9200.packet_bits() == 23 * 8
    assert LYRA_V2_3200.packet_bits() == 8 * 8


def test_packet_bits_with_overhead():
    assert LYRA_V2_9200.packet_bits(1, 12.0) == (23 + 12) * 8


def test_batching_amortizes_overhead_per_frame():
    one = LYRA_V2_9200.packet_bits(1, 12.0) / 1
    four = LYRA_V2_9200.packet_bits(4, 12.0) / 4
    assert four < one  # overhead spread across more frames


def test_frame_ms_is_calibratable():
    c = CodecProfile("custom", 9200, frame_ms=40.0)
    assert c.payload_bytes == pytest.approx(46.0)
    assert c.frames_per_second == pytest.approx(25.0)


def test_validation():
    with pytest.raises(ValueError):
        CodecProfile("bad", 0)
    with pytest.raises(ValueError):
        CodecProfile("bad", 9200, frame_ms=0)
    with pytest.raises(ValueError):
        LYRA_V2_9200.packet_bits(0)
    with pytest.raises(ValueError):
        LYRA_V2_9200.packet_bits(1, -1)


def test_by_name():
    assert by_name("lyra_v2_9.2k") is LYRA_V2_9200
    with pytest.raises(KeyError):
        by_name("nope")
