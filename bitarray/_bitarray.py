default_endian = 'big'


def bits2bytes(__n):
    if not isinstance(__n, int):
        raise TypeError("integer expected")
    if __n < 0:
        raise ValueError("non-negative integer expected")
    return (__n + 7) // 8

def check_endian(s):
    if s not in ('little', 'big'):
        raise ValueError("bit endianness must be either "
                         "'little' or 'big', not '%s'", s)

class bitarray:

    def __init__(self, initial=0, /, endian=default_endian, buffer=None):
        check_endian(endian)
        self._endian = endian

        if isinstance(initial, bool):
            raise TypeError("cannot create bitarray from bool")

        if initial is None:
            self._nbits = 0
            self._buffer = bytearray()

        if isinstance(initial, int):
            self._nbits = initial
            self._buffer = bytearray(bits2bytes(initial))

        self._nbits = 0
        self._buffer = bytearray()
        self.extend_dispatch(initial)

    def extend_dispatch(self, a):
        ...


def get_default_endian():
    return default_endian

def _set_default_endian(s: str):
    global default_endian
    check_endian(s)
    default_endian = s
