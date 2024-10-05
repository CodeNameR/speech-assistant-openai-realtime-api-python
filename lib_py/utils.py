import base64
import random
from typing import Union

class RealtimeUtils:
    @staticmethod
    def float_to_16bit_pcm(float32_array: list) -> bytes:
        buffer = bytearray()
        for s in float32_array:
            s = max(-1.0, min(1.0, s))
            int_val = int(s * 32768) if s < 0 else int(s * 32767)
            buffer += int_val.to_bytes(2, byteorder='little', signed=True)
        return bytes(buffer)

    @staticmethod
    def base64_to_array_buffer(base64_str: str) -> bytes:
        return base64.b64decode(base64_str)

    @staticmethod
    def array_buffer_to_base64(array_buffer: Union[bytes, bytearray]) -> str:
        return base64.b64encode(array_buffer).decode('ascii')

    @staticmethod
    def merge_int16_arrays(left: bytes, right: bytes) -> bytes:
        if not isinstance(left, bytes) or not isinstance(right, bytes):
            raise ValueError("Both left and right must be bytes representing Int16Arrays")
        return left + right

    @staticmethod
    def generate_id(prefix: str, length: int = 21) -> str:
        if length <= len(prefix):
            raise ValueError("Length must be greater than the length of the prefix")
        chars = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
        str_suffix = ''.join(random.choice(chars) for _ in range(length - len(prefix)))
        return f"{prefix}{str_suffix}"