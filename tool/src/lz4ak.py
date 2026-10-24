"""Bounded decoder for Arknights' LZ4 token/offset variant.

Format reference: isHarryh/Ark-Unpacker src/lz4ak/Block.py (BSD-3-Clause).
See tools/Ark-Unpacker-LICENSE.txt. No game schemas are used.
"""
import lz4.block


def decompress(data, uncompressed_size):
    data = bytearray(data)
    i = produced = 0

    def extra(pos):
        total = 0
        while True:
            if pos >= len(data):
                raise ValueError("Truncated LZ4AK length")
            value = data[pos]
            pos += 1
            total += value
            if value != 255:
                return total, pos

    while i < len(data):
        literal, match = data[i] & 15, data[i] >> 4
        data[i] = (literal << 4) | match
        i += 1
        if literal == 15:
            length, i = extra(i)
            literal += length
        i += literal
        produced += literal
        if i > len(data) or produced > uncompressed_size:
            raise ValueError("Invalid LZ4AK literal length")
        if produced == uncompressed_size:
            break
        if i + 2 > len(data):
            raise ValueError("Truncated LZ4AK offset")
        offset = (data[i] << 8) | data[i + 1]
        if not 0 < offset <= produced:
            raise ValueError("Invalid LZ4AK match offset")
        data[i], data[i + 1] = data[i + 1], data[i]
        i += 2
        if match == 15:
            length, i = extra(i)
            match += length
        produced += match + 4
        if produced > uncompressed_size:
            raise ValueError("Invalid LZ4AK match length")
    result = lz4.block.decompress(bytes(data), uncompressed_size=uncompressed_size)
    if len(result) != uncompressed_size:
        raise ValueError("LZ4AK output length mismatch")
    return result


def install():
    from UnityPy.helpers import CompressionHelper
    CompressionHelper.DECOMPRESSION_MAP[4] = decompress
