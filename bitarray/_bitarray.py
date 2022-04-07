from bitarray._header import __version__, getbit, setbit, reverse_table


default_endian = 1


def bits2bytes(n: int, /) -> int:
    if not isinstance(n, int):
        raise TypeError("integer expected")
    if n < 0:
        raise ValueError("non-negative integer expected")
    return (n + 7) // 8

def endian_from_string(s: str) -> int:
    if s == 'little':
        return 0
    if s == 'big':
        return 1
    raise ValueError("bit endianness must be either "
                     "'little' or 'big', not '%s'", s)

class bitarray:

    def __init__(self, initial=0, /, endian: str='big', buffer=None):
        self._endian = endian_from_string(endian)

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
        self._extend_dispatch(initial)

    def _resize(self, nbits: int):
        size: int = len(self._buffer)
        newsize: int = bits2bytes(nbits)

        if newsize == size:  # buffer size hasn't changed - bypass everything
            self._nbits = nbits
            return

        if newsize > size:
            self._buffer.extend(bytearray(newsize - size))
        else:
            del self._buffer[newsize:]

    def bytereverse(self, a: int, b: int):
        self._buffer[a:b] = self._buffer[a:b].translate(reverse_table)

    def _copy_n(self, a: int, other, b: int, n: int):
        assert 0 <= a <= self._nbits
        assert 0 <= b <= other._nbits
        assert n >= 0
        if n == 0 or (self is other and a == b):
            return

        if a <= b:  # loop forward
            for i in range(n):
                self[i + a] = other[i + b]
        else:       # loop backwards
            for i in range(n - 1, -1, -1):
                self[i + a] = other[i + b]

    def _delete_n(self, start: int, n: int):
        nbits: int = self._nbits

        assert 0 <= start and start <= nbits
        assert 0 <= n and n <= nbits - start
        assert start != nbits or n == 0  # start == nbits implies n == 0

        self.copy_n(start, self, start + n, nbits - start - n)
        self._resize(nbits - n);

    def _insert_n(self, start :int, n: int):
        nbits: int = self._nbits

        assert 0 <= start and start <= nbits
        assert n >= 0

        self._resize(nbits + n)
        self._copy_n(start + n, self, start, nbits - start)

    def _extend_bitarray(self, other):
        self_nbits: int = self._nbits
        other_nbits: int = other._nbits

        self._resize(self_nbits + other_nbits)
        self._copy_n(self_nbits, other, 0, other_nbits)

    def _entend_iter(self, iterator):
        ...

    def _extend_01(self, s: str):
        for c in s:
            vi: int = -1
            if c == '0': vi = 0
            if c == '1': vi = 1
            if c in ('_', ' ', '\n', '\r',  '\t', '\v'):
                continue
            if vi > 0:
                self._resize(self._nbits + 1)
                setbit(self, self._nbits - 1, vi)
                continue
            raise ValueError("expected '0' or '1' (or whitespace, or "
                             "underscore), got '%c' (0x%02x)", chr(c), c);

    def _extend_dispatch(self, obj):
        if isinstance(obj, bitarray):
            self._extend_bitarray(obj)

        elif isinstance(obj, bytes):
            raise TypeError("cannot extend bitarray with 'bytes', "
                            "use .pack() or .frombytes() instead")

        elif isinstance(obj, str):
            self._extend_01(obj)

        else:
            raise TypeError("'%s' object is not iterable" % type(obj).__name__)


def get_default_endian():
    return 'big' if default_endian else 'little'

def _set_default_endian(s: str, /):
    global default_endian
    default_endian = endian_from_string(s)
