"""FIT reader: corrupt and malformed files fail clearly (fitdecode agreeing where it can tell), and
the CRC and profile constants agree with independent references."""

from datetime import datetime, timezone

import fitdecode
import numpy as np
import pytest
from fit_kit import HYDE_PARK, START, activity, oracle
from fit_writer import MESG_RECORD, FitWriter, crc16

from placewise.constants import fit as fit_constants
from placewise.io._fit_decode import crc16 as _crc16
from placewise.io.fit import FitError, read_fit

# --- corrupt and malformed files ---


def test_corrupt_crc_fails_clearly():
    data = bytearray(activity())
    data[60] ^= 0x01  # one bit, inside the data records
    with pytest.raises(fitdecode.FitCRCError):
        oracle(bytes(data))  # fitdecode agrees the file is corrupt
    with pytest.raises(FitError, match="CRC"):
        read_fit(bytes(data))
    assert issubclass(FitError, ValueError)
    stored = bytearray(activity())
    stored[-1] ^= 0xFF  # the stored file CRC itself
    with pytest.raises(FitError, match="CRC"):
        read_fit(bytes(stored))


def test_corrupt_header_crc_fails_clearly():
    data = bytearray(activity())
    data[12] ^= 0x01
    with pytest.raises(FitError, match="header CRC"):
        read_fit(bytes(data))


def test_check_crc_can_be_turned_off():
    data = bytearray(activity())
    data[-1] ^= 0xFF
    assert len(read_fit(bytes(data), check_crc=False).track) == len(HYDE_PARK)


def test_malformed_files():
    data = activity()
    with pytest.raises(FitError, match="FIT"):
        read_fit(b"not a fit file at all")
    with pytest.raises(FitError, match=r"\.FIT"):
        read_fit(data[:8] + b"XFIT" + data[12:])
    with pytest.raises(FitError, match="truncated"):
        read_fit(data[:-10])
    w = FitWriter()
    w.define(0, MESG_RECORD, [(253, "uint32")])
    w.message(0, {253: START})
    body = bytearray(w.to_bytes())
    body[14 + 9] = 0x05  # the data message now names local message 5, never defined
    body[-2:] = crc16(bytes(body[:-2])).to_bytes(2, "little")
    with pytest.raises(FitError, match="local message 5"):
        read_fit(bytes(body))


# --- internals checked against independent references ---


@pytest.mark.parametrize("n", [0, 1, 2, 15, 16, 17, 255, 1000, 4097, 100_003])
def test_crc_matches_the_sdk_nibble_algorithm(n):
    data = np.random.default_rng(n).integers(0, 256, n, dtype=np.uint8).tobytes()
    assert _crc16(data) == crc16(data)


def test_profile_constants_agree_with_fitdecode():
    from fitdecode import profile

    for mesg_num, fields in fit_constants.MESSAGE_FIELDS.items():
        theirs = profile.MESSAGE_TYPES[mesg_num]
        for num, field in fields.items():
            reference = theirs.fields[num]
            assert field.name == reference.name, (mesg_num, num)
            assert field.scale == (reference.scale or 1), field.name
            assert field.offset == (reference.offset or 0), field.name
    for number, name in fit_constants.SPORTS.items():
        assert profile.FIELD_TYPES["sport"].enum[number] == name
    for number, name in fit_constants.MANUFACTURERS.items():
        assert profile.FIELD_TYPES["manufacturer"].enum[number] == name
    for number, name in fit_constants.FILE_TYPES.items():
        assert profile.FIELD_TYPES["file"].enum[number] == name
    assert fit_constants.EPOCH_UNIX_S == datetime(1989, 12, 31, tzinfo=timezone.utc).timestamp()
