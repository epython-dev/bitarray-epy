import sys

from bitarray._header import (
    getbit, setbit, zeroed_last_byte, setunused, bitcount_lookup,
    reverse_table, normalize_index, check_bit,
)


default_endian = 1

Py_LT = 1
Py_LE = 2
Py_EQ = 3
Py_NE = 4
Py_GT = 5
Py_GE = 6


def bits2bytes(n: int, /) -> int:
    if not isinstance(n, int):
        raise TypeError("integer expected")
    if n < 0:
        raise ValueError("non-negative integer expected")
    return (n + 7) // 8

def endian_from_string(s: str) -> int:
    if s is '<default>':
        return default_endian
    if s == 'little':
        return 0
    if s == 'big':
        return 1
    raise ValueError("bit endianness must be either "
                     "'little' or 'big', not '%s'", s)

def calc_slicelength(start: int, stop: int, step: int):
    assert step < 0 or (start >= 0 and stop >= 0)    # step > 0
    assert step > 0 or (start >= -1 and stop >= -1)  # step < 0
    assert step != 0

    if step < 0:
        if stop < start:
            return (start - stop - 1) // (-step) + 1
    else:
        if start < stop:
            return (stop - start - 1) // step + 1

    return 0

def make_step_positive(slicelength: int, start: int, stop: int, step: int):
    if step < 0:
        stop = start + 1
        start = stop + step * (slicelength - 1) - 1
        step = -step

    assert start >= 0 and stop >= 0 and step > 0 and slicelength >= 0
    assert calc_slicelength(start, stop, step) == slicelength
    return start, stop, step


class bitarray:

    def __init__(self, initial=0, /, endian: str='<default>'):
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

        if isinstance(initial, bitarray) and endian == '<default>':
            self._endian = initial._endian

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
                setbit(self, i + a, getbit(other, i + b))
        else:       # loop backwards
            for i in range(n - 1, -1, -1):
                setbit(self, i + a, getbit(other, i + b))

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

        self._copy_n(start, self, start + n, nbits - start - n)
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
        org_bits: int = self._nbits
        for c in s:
            vi: int = -1
            if c == '0': vi = 0
            if c == '1': vi = 1
            if c in ('_', ' ', '\n', '\r',  '\t', '\v'):
                continue
            if vi < 0:
                self._resize(org_bits)
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

    def _richcompare(self, other, op):
        if not isinstance(other, bitarray):
            raise NotImplementedError

        vs: int = self._nbits
        ws: int = other._nbits

        if op == Py_EQ or op == Py_NE:
            if vs != ws:
                return op == Py_NE

            if self._endian == other._endian:
                cmp = self._buffer[:vs // 8] != other._buffer[:vs // 8]
                if cmp == 0 and vs % 8:
                    cmp = zeroed_last_byte(self) != zeroed_last_byte(other)

                return bool(cmp == 0) ^ bool(op == Py_NE)

        for i in range(min(vs, ws)):
            vi: int = getbit(self, i)
            wi: int = getbit(other, i)

            if vi != wi:
                if op == Py_LT:   cmp = v1 <  wi
                elif op == Py_LE: cmp = vi <= wi
                elif op == Py_EQ: cmp = 0
                elif op == Py_NE: cmp = 1
                elif op == Py_GT: cmp = vi >  wi
                elif op == Py_GE: cmp = vi >= wi
                else: exit("Py_UNREACHABLE")
                return bool(cmp)

        if op == Py_LT:   cmp = vs <  ws
        elif op == Py_LE: cmp = vs <= ws
        elif op == Py_EQ: cmp = vs == ws
        elif op == Py_NE: cmp = vs != ws
        elif op == Py_GT: cmp = vs >  ws
        elif op == Py_GE: cmp = vs >= ws
        else: exit("Py_UNREACHABLE")
        return bool(cmp)

    # ------------------- Implementation of bitarray methods ---------------

    def append(self, vi: int):
        check_bit(vi)
        self._resize(self._nbits + 1)
        setbit(self, self._nbits - 1, vi)

    def bytereverse(self, a: int, b: int):
        self._buffer[a:b] = self._buffer[a:b].translate(reverse_table)

    def clear(self):
        self._resize(0)

    def copy(self):
        res = bitarray(self._nbits, self.endian())
        res._buffer = bytearray(self._buffer)

    def count(self, vi: int = 1,
              start: int = 0, stop: int = sys.maxsize, step: int = 1) -> int:
        check_bit(vi)

        start = normalize_index(self._nbits, step, start)
        stop  = normalize_index(self._nbits, step, stop)

        if step == 1:
            return self._count(vi, start, stop)
        if step == 0:
            raise ValueError("count step cannot be zero")
        else:
            slicelength: int = calc_slicelength(start, stop, step)
            cnt: int = 0

            start, stop, step = make_step_positive(slicelength,
                                                   start, stop, step)
            for i in range(start, stop, step):
                cnt += getbit(self, i)

            return cnt if vi else slicelength - cnt

    def endian(self) -> str:
        return 'big' if self._endian else 'little'

    def extend(self, obj):
        self._extend_dispatch(obj)

    def fill(self) -> int:
        p: int = setunused(self)
        self._resize(self._nbits + p)
        return p

    def insert(self, i :int, vi: int):
        i = normalize_index(self._nbits, 1, i)
        check_bit(vi)
        self._insert_n(i, 1)
        setbit(self, i, vi)

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

    def setall(self, vi: int):
        check_bit(vi)
        for i in range(len(self._buffer)):
            self._buffer[i] = 0xff if vi else 0x00

    def to01(self):
        return ''.join(str(getbit(self, i)) for i in range(self._nbits))

    def tolist(self):
        return [getbit(self, i) for i in range(self._nbits)]

    def tobytes(self):
        setunused(self)
        return bytes(self._buffer)

    def frombytes(self, data: bytes):
        nbytes: int = len(data)
        if nbytes == 0:
            return

        t: int = self._nbits
        p: int = 8 * bits2bytes(t) - t
        assert 0 <= p < 8
        self._resize(t + p)
        assert self._nbits % 8 == 0
        self._nbits += 8 * nbytes
        self._buffer += data
        self._delete_n(t, p)

    def unpack(self, zero=b'\0', one=b'\1') -> bytes:
        if not (isinstance(zero, bytes) and isinstance(one, bytes)):
            raise TypeError
        res = bytearray()
        for i in range(self._nbits):
            res.append(ord(one if getbit(self, i) else zero))
        return bytes(res)

    def pack(self, data: bytes):
        if not isinstance(data, bytes):
            raise TypeError
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
        self._delete_n(i, 1)
        return vi

    def __add__(self, other):
        res = self.copy()
        res._extend_dispatch(other)
        return res

    def __iadd__(self, other):
        self._extend_dispatch(other)

    def __mul__(self, n: int):
        if not isinstance(n, int):
            raise TypeError
        ...

    def __delitem__(self, a):
        if isinstance(a, int):
            if a < 0 or a >= self._nbits:
                raise IndexError("bitarray assignment index out of range")
            self._delete_n(a, 1)

        elif isinstance(a, slice):
            start, stop, step = a.indices(self._nbits)
            slicelength: int = calc_slicelength(start, stop, step)
            start, stop, step = make_step_positive(slicelength,
                                                   start, stop, step)
            if step == 1:
                self._delete_n(start, stop - start)
            else:
                assert step > 1
                i = j = start
                while i < self._nbits:
                    if (i - start) % step != 0 or i >= stop:
                        setbit(self, j, getbit(self, i))
                        j += 1
                    i += 1
                self._resize(self._nbits - slicelength)
        else:
            TypeError("bitarray or int expected for slice assignment, not %s",
                      type(a).__name__)

    def __getitem__(self, a):
        if isinstance(a, int):
            if a < 0 or a >= self._nbits:
                raise IndexError("bitarray index out of range")
            return getbit(self, a)

        if isinstance(a, slice):
            return ...

        raise TypeError("bitarray indices must be integers or slices, not %s",
                        type(item).__name__)

    def __contains__(self, other):
        ...

    def __lt__(self, other):
        return self._richcompare(other, Py_LT)

    def __le__(self, other):
        return self._richcompare(other, Py_LE)

    def __eq__(self, other):
        return self._richcompare(other, Py_EQ)

    def __ne__(self, other):
        return self._richcompare(other, Py_NE)

    def __gt__(self, other):
        return self._richcompare(other, Py_GT)

    def __ge__(self, other):
        return self._richcompare(other, Py_GE)


def get_default_endian():
    return 'big' if default_endian else 'little'

def _set_default_endian(s: str, /):
    global default_endian
    default_endian = endian_from_string(s)
