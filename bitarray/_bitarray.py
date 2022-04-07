from bitarray._header import (
    getbit, setbit, setunused, reverse_table, pybit_as_int
)

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
            return

        if isinstance(initial, int):
            self._nbits = initial
            self._buffer = bytearray(bits2bytes(initial))
            return

        self._nbits = 0
        self._buffer = bytearray()
        self._extend_dispatch(initial)

    def _resize(self, nbits: int):
        size: int = len(self._buffer)
        newsize: int = bits2bytes(nbits)

        self._nbits = nbits

        if newsize > size:
            self._buffer.extend(bytearray(newsize - size))
        if newsize < size:
            del self._buffer[newsize:]

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

    def _count(self, vi: int, a: int, b:int):
        res: int = 0
        assert 0 <= a <= self._nbits
        assert 0 <= b <= self._nbits
        if a >= b:
            return 0

        if b >= a + 8:
            byte_a: int = bits2bytes(a)
            byte_b: int = b // 8

            res += self._count(1, a, 8 * byte_a)
            for i in range(byte_a, byte_b):
                res += bitcount_lookup[self._buffer[i]]
            res += self._count(1, 8 * byte_b, b)
        else:
            for i in range(a, b):
                res += getbit(self, i)

        return res if vi else b - a - res

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
            if vi < 0:
                raise ValueError("expected '0' or '1' (or whitespace, or "
                        "underscore), got '%s' (0x%02x)" % (c, ord(c)));
            self._resize(self._nbits + 1)
            setbit(self, self._nbits - 1, vi)

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

    # ------------------- Implementation of bitarray methods ---------------

    def append(self, value):
        vi :int = pybit_as_int(value)
        self._resize(self._nbits + 1)
        setbit(self, self._nbits - 1, vi)

    def bytereverse(self, a: int, b: int):
        self._buffer[a:b] = self._buffer[a:b].translate(reverse_table)

    def clear(self):
        self._resize(0)

    def copy(self):
        res = bitarray(self._nbits, self._endian)
        res._buffer = bytearray(self._buffer)

    def count(self, value: int = 1,
              start: int = 0, stop = None, step: int = 1) -> int:
        vi: int = pybit_as_int(value)
        if stop is None:
            stop = self._nbits

        if step == 1:
            return self._count(vi, start, stop)
        else:
            ...

    def endian(self) -> str:
        return 'big' if self._endian else 'little'

    def extend(self, obj):
        self._extend_dispatch(obj)

    def fill(self) -> int:
        p: int = setunused(self)
        self._resize(self, self._nbits + p)
        return p

    def insert(self, i :int, value):
        vi :int = pybit_as_int(value)
        ...

    def invert(self, i = None):
        if i is None:
            for x in range(len(self._buffer)):
                self._buffer[x] ^= 0xff
            return

        if i < 0:
            i += self._nbits

        if i < 0 or i >= self._nbits:
            raise IndexError("index out of range")

        setbit(self, i, not getbit(self, i))

    def __len__(self) -> int:
        return self._nbits

    def __memoryview__(self) -> memoryview: # XXX
        return memoryview(self._buffer)

    def __repr__(self) -> str:
        if self._nbits == 0:
            return 'bitarray()'

        res = ["bitarray('"]
        for i in range(self._nbits):
            res.append('1' if getbit(self, i) else '0')
        res.append("')")
        return ''.join(res)

    def reverse(self):
        i :int = 0
        j :int = self._nbits - 1
        while i < j:
            t: int = getbit(self, i)
            setbit(self, i, getbit(self, j))
            setbit(self, j, t)
            i += 1
            j -= 1

    def setall(self, value: int):
        vi: int = pybit_as_int(value)
        for i in range(len(self._buffer)):
            self._buffer[i] = 0xff if vi else 0x00

    def tobytes(self):
        setunused(self)
        return bytes(self._buffer)

    def tolist(self):
        return [getbit(self, i) for i in range(self._nbits)]

    def unpack(self, zero=b'\0', one=b'\1') -> bytes:
        res = bytearray()
        for i in range(self._nbits):
            res.append(one if getbit(self, i) else zero)
        return bytes(res)

    def pack(self, data: bytes):
        nbits: int = self._nbits
        nbytes: int = len(data)

        self._resize(nbits + nbytes)

        for i in range(nbytes):
            setbit(self, nbits + i, data[i])

    def pop(self, i: int = -1):
        if self._nbits == 0:
            raise IndexError("pop from empty bitarray")

        if i < 0:
            i += self._nbits

        if i < 0 or i >= self._nbits:
            raise IndexError("pop index out of range")

        vi = getbit(self, i)
        self._delete_n(self, i, 1)
        return vi

def get_default_endian():
    return 'big' if default_endian else 'little'

def _set_default_endian(s: str, /):
    global default_endian
    default_endian = endian_from_string(s)
