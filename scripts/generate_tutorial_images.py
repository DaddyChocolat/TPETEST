import os
import zlib
import struct
from pathlib import Path

path = Path('assets/textures')
path.mkdir(parents=True, exist_ok=True)


def write_png(file_path, color):
    width, height = 640, 360
    raw_data = b''.join(
        b'\x00' + bytes([color[0], color[1], color[2]]) * width
        for _ in range(height)
    )
    compressor = zlib.compress(raw_data)

    def chunk(c_type, data):
        chunk_data = struct.pack('>I', len(data)) + c_type + data
        crc = zlib.crc32(c_type + data) & 0xFFFFFFFF
        return chunk_data + struct.pack('>I', crc)

    with open(file_path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)))
        f.write(chunk(b'IDAT', compressor))
        f.write(chunk(b'IEND', b''))

for i, color in enumerate([(40, 80, 140), (70, 120, 60), (140, 80, 40)], start=1):
    write_png(path / f'tutorial{i}.png', color)

print('tutorial images created')
