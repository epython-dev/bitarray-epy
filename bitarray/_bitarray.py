from sys import maxsize

from bitarray._header import (
    getbit, setbit, zeroed_last_byte, setunused,
    bitmask_table, ones_table, bitcount_lookup,
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
    if not isinstance(s, str):
        raise TypeError
    if s == '<default>':
        return default_endian
    if s == 'little':
        return 0
    if s == 'big':
        return 1
    raise ValueError("bit endianness must be either "
                     "'little' or 'big', not '%s'" % s)

def calc_slicelength(start: int, stop: int, step: int) -> int:
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

    def _shift_r8(self, a: int, b: int, n: int):
        assert 0 <= n and n < 8 and a <= b
        assert 0 <= a and a <= len(self._buffer)
        assert 0 <= b and b <= len(self._buffer)
        if n == 0 or a == b:
            return

        if self._endian:
            self.bytereverse(a, b)

        buff = self._buffer
        for i in range(b - 1, a - 1, -1):
            buff[i] = (buff[i] << n) % 0x100
            if i != a:
                buff[i] |= buff[i - 1] >> (8 - n)

        if self._endian:
            self.bytereverse(a, b)

    def _copy_n(self, a: int, other, b: int, n: int):
        assert 0 <= a <= self._nbits
        assert 0 <= b <= other._nbits
        assert n >= 0
        if n == 0 or (self is other and a == b):
            return

        if a % 8 == 0 and b % 8 == 0:            # aligned case
            p1: int = a // 8
            p2: int = (a + n - 1) // 8
            m: int = bits2bytes(n)

            assert p1 + m == p2 + 1
            m2 = ones_table[self._endian][(a + n) % 8]
            t2 = self._buffer[p2]

            self._buffer[p1:p1 + m] = other._buffer[b // 8:b // 8 + m]
            if self._endian != other._endian:
                self.bytereverse(p1, p2 + 1)

            if m2:
                self._buffer[p2] = (self._buffer[p2] & m2) | (t2 & ~m2)
            return

        if n < 8:                                # small n case
            if a <= b:  # loop forward
                for i in range(n):
                    setbit(self, i + a, getbit(other, i + b))
            else:       # loop backwards
                for i in range(n - 1, -1, -1):
                    setbit(self, i + a, getbit(other, i + b))
            return

        # -------------------------------------- # general case
        p1: int = a // 8
        p2: int = (a + n - 1) // 8
        p3: int = b // 8
        sa: int = a % 8
        sb: int = -(b % 8)
        m1: int = ones_table[self._endian][sa]
        m2: int = ones_table[self._endian][(a + n) % 8]

        assert n >= 8
        assert a - sa == 8 * p1
        assert b + sb == 8 * p3
        assert a + n > 8 * p2

        t1: int = self._buffer[p1]
        t2: int = self._buffer[p2]
        t3: int = other._buffer[p3]

        if sa + sb < 0:
            sb += 8
        self._copy_n(a - sa, other, b + sb, n - sb)
        self._shift_r8(p1, p2 + 1, sa + sb)

        if m1:
            self._buffer[p1] = (self._buffer[p1] & ~m1) | (t1 & m1)

        if m2 and sa + sb:
            self._buffer[p2] = (self._buffer[p2] & m2) | (t2 & ~m2)

        for i in range(sb):
            setbit(self, i + a, t3 & bitmask_table[other._endian][(i + b) % 8])

    def _delete_n(self, start: int, n: int):
        nbits: int = self._nbits

        assert 0 <= start and start <= nbits
        assert 0 <= n and n <= nbits - start
        assert start != nbits or n == 0  # start == nbits implies n == 0

        self._copy_n(start, self, start + n, nbits - start - n)
        self._resize(nbits - n)

    def _insert_n(self, start :int, n: int):
        nbits: int = self._nbits

        assert 0 <= start and start <= nbits
        assert n >= 0

        self._resize(nbits + n)
        self._copy_n(start + n, self, start, nbits - start)

    def _repeat(self, m: int):
        k: int = self._nbits

        if k == 0 or m == 1:  # nothing to do
            return 0

        if m <= 0:            # clear
            return self._resize(0)

        assert m > 1 and k > 0
        if k >= maxsize // m:
            raise OverflowError("cannot repeat bitarray (of size %d) "
                                "%d times" % (k, m))

        q: int = k * m  # number of resulting bits
        self._resize(q)

        while k <= q // 2:  # double copies
            self._copy_n(k, self, 0, k)
            k *= 2
        assert q // 2 < k and k <= q

        self._copy_n(k, self, 0, q - k)  # copy remaining bits

    def _setrange(self, a: int, b: int, vi: int):
        assert 0 <= a <= self._nbits
        assert 0 <= b <= self._nbits

        if b >= a + 8:
            byte_a: int = bits2bytes(a)
            byte_b: int = b // 8

            self._setrange(a, 8 * byte_a, vi)
            self._buffer[byte_a:byte_b] = (
                (byte_b - byte_a) * (b'\xff' if vi else b'\0'))
            self._setrange(8 * byte_b, b, vi)
        else:
            for i in range(a, b):
                setbit(self, i, vi)

    def _count(self, vi: int, a: int, b:int) -> int:
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

    def _find_bit(self, vi: int, a: int, b: int) -> int:
        n: int = b - a
        assert 0 <= a and a <= self._nbits
        assert 0 <= b and b <= self._nbits
        assert 0 <= vi and vi <= 1
        if n <= 0:
            return -1

        if n > 8:
            byte_a: int = bits2bytes(a)
            byte_b: int = b // 8
            c: int = 0x00 if vi else 0xff

            res = self._find_bit(vi, a, 8 * byte_a)
            if res >= 0:
                return res

            for i in range(byte_a, byte_b):  # skip bytes
                if c ^ self._buffer[i]:
                    return self._find_bit(vi, 8 * i, 8 * i + 8)

            return self._find_bit(vi, 8 * byte_b, b)

        assert n <= 8
        for i in range(a, b):
            if getbit(self, i) == vi:
                return i

        return -1

    def _find(self, xa, start: int, stop: int) -> int:
        assert 0 <= start and start <= self._nbits
        assert 0 <= stop and stop <= self._nbits

        if xa._nbits == 1:  # faster for sparse bitarrays
            return self._find_bit(getbit(xa, 0), start, stop)

        while start <= stop - xa._nbits:
            for i in range(xa._nbits):
                if getbit(self, start + i) != getbit(xa, i):
                    break
            else:
                return start
            start += 1

        return -1

    def _extend_bitarray(self, other):
        self_nbits: int = self._nbits
        other_nbits: int = other._nbits

        self._resize(self_nbits + other_nbits)
        self._copy_n(self_nbits, other, 0, other_nbits)

    def _extend_iter(self, iterator):
        org_bits: int = self._nbits
        for vi in iterator:
            if not isinstance(vi, int):
                self._resize(org_bits)
                raise TypeError
            if vi < 0 or vi > 1:
                self._resize(org_bits)
                raise ValueError("bit must be 0 or 1, got %d" % vi)
            self._resize(self._nbits + 1)
            setbit(self, self._nbits - 1, vi)

    def _extend_01(self, s: str):
        org_bits: int = self._nbits
        ignore = {ord(c) for c in '_ \n\r\t\v'}
        for c in s.encode('ascii'):
            vi: int = -1
            if c == ord('0'): vi = 0
            if c == ord('1'): vi = 1
            if c in ignore:
                continue
            if vi < 0:
                self._resize(org_bits)
                raise ValueError("expected '0' or '1' (or whitespace, or "
                        "underscore), got '%s' (0x%02x)" % (chr(c), c))
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

        elif hasattr(obj, '__iter__'):
            self._extend_iter(obj)

        else:
            raise TypeError("'%s' object is not iterable" % type(obj).__name__)

    def _richcompare(self, other, op):
        if not isinstance(other, bitarray):
            return NotImplemented

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
                if op == Py_LT:   cmp = vi <  wi
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

    def all(self) -> bool:
        return self._find_bit(0, 0, self._nbits) == -1

    def any(self) -> bool:
        return self._find_bit(1, 0, self._nbits) >= 0

    def append(self, vi: int):
        check_bit(vi)
        self._resize(self._nbits + 1)
        setbit(self, self._nbits - 1, vi)

    def bytereverse(self, a: int = 0, b: int = maxsize):
        nbytes: int = len(self._buffer)
        if b == maxsize:
            b = nbytes

        if a < 0 or a > nbytes or b < 0 or b > nbytes:
            raise IndexError("byte index out of range")

        self._buffer[a:b] = self._buffer[a:b].translate(reverse_table)

    def clear(self):
        self._resize(0)

    def copy(self):
        res = bitarray(self._nbits, self.endian())
        res._buffer = bytearray(self._buffer)
        return res

    def count(self, vi: int = 1,
              start: int = 0, stop: int = maxsize, step: int = 1) -> int:
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

    def find(self, x, start: int = 0, stop: int = maxsize):
        start = normalize_index(self._nbits, 1, start)
        stop = normalize_index(self._nbits, 1, stop)

        if isinstance(x, int):
            check_bit(x)
            return self._find_bit(x, start, stop)

        if isinstance(x, bitarray):
            return self._find(x, start, stop)

        raise TypeError("bitarray or int expected, not '%s'" %
                        type(x).__name__)

    def index(self, *args):
        res = self.find(*args)
        if res < 0:
            raise ValueError("%r not in bitarray" % (args[0]))
        return res

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

        res = bytearray(b"bitarray('")
        for i in range(self._nbits):
            res.append(ord('1') if getbit(self, i) else ord('0'))
        res.extend(b"')")
        return res.decode('ascii')

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
        self._buffer[:] = len(self._buffer) * (b'\xff' if vi else b'\0')

    def sort(self, reverse=False):
        if not isinstance(reverse, int):
            raise TypeError
        cnt: int = self._count(reverse, 0, self._nbits)
        self._setrange(0, cnt, reverse)
        self._setrange(cnt, self._nbits, not reverse)

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

    def remove(self, vi: int):
        check_bit(vi)
        i: int = self._find_bit(vi, 0, self._nbits)
        if i < 0:
            raise ValueError("%d not in bitarray" % vi)
        self._delete_n(i, 1)

    def __add__(self, other):
        res = self.copy()
        res._extend_dispatch(other)
        return res

    def __iadd__(self, other):
        self._extend_dispatch(other)
        return self

    def __mul__(self, n: int):
        if not isinstance(n, int):
            raise TypeError
        res = self.copy()
        res._repeat(n)
        return res

    __rmul__ = __mul__

    def __imul__(self, n: int):
        if not isinstance(n, int):
            raise TypeError
        self._repeat(n)
        return self

    def __delitem__(self, item):
        if isinstance(item, int):
            if item < 0:
                item += self._nbits
            if item < 0 or item >= self._nbits:
                raise IndexError("bitarray assignment index out of range")
            self._delete_n(item, 1)

        elif isinstance(item, slice):
            start, stop, step = item.indices(self._nbits)
            slicelength: int = calc_slicelength(start, stop, step)
            start, stop, step = make_step_positive(slicelength,
                                                   start, stop, step)
            if step == 1:
                self._delete_n(start, slicelength)
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
            raise TypeError("bitarray or int expected for slice assignment, "
                            "not %s" % type(item).__name__)

    def __getitem__(self, item):
        if isinstance(item, int):
            if item < 0:
                item += self._nbits
            if item < 0 or item >= self._nbits:
                raise IndexError("bitarray index out of range")
            return getbit(self, item)

        if isinstance(item, slice):
            start, stop, step = item.indices(self._nbits)
            slicelength: int = calc_slicelength(start, stop, step)

            res = bitarray(slicelength, self.endian())
            if step == 1:
                res._copy_n(0, self, start, slicelength)
            else:
                i = 0
                j = start
                while i < slicelength:
                    setbit(res, i, getbit(self, j))
                    i += 1
                    j += step
            return res

        raise TypeError("bitarray indices must be integers or slices, "
                        "not %s" % type(item).__name__)

    def _setslice_bitarray(self, sl, other):
        start, stop, step = sl.indices(self._nbits)
        slicelength: int = calc_slicelength(start, stop, step)

        increase: int = other._nbits - slicelength

        other = other.copy()

        if step == 1:
            if increase > 0:
                self._insert_n(start + slicelength, increase)
            if increase < 0:
                self._delete_n(start + other._nbits, -increase)
            self._copy_n(start, other, 0, other._nbits)
        else:
            if increase != 0:
                raise ValueError("attempt to assign sequence of "
                                 "size %d to extended slice of size %d" %
                                 (other._nbits, slicelength))
            i = 0
            j = start
            while i < slicelength:
                setbit(self, j, getbit(other, i))
                i += 1
                j += step

    def _setslice_bool(self, sl, vi):
        check_bit(vi)
        start, stop, step = sl.indices(self._nbits)
        slicelength: int = calc_slicelength(start, stop, step)
        start, stop, step = make_step_positive(slicelength,
                                               start, stop, step)
        for i in range(start, stop, step):
            setbit(self, i, vi)

    def __setitem__(self, item, value):
        if isinstance(item, int):
            if item < 0:
                item += self._nbits
            if item < 0 or item >= self._nbits:
                raise IndexError("bitarray assignment index out of range")
            check_bit(value)
            setbit(self, item, value)

        elif isinstance(item, slice):
            if isinstance(value, bitarray):
                self._setslice_bitarray(item, value)
            elif isinstance(value, int):
                self._setslice_bool(item, value)
            else:
                raise TypeError("bitarray or int expected, got %s" %
                                type(value).__name__)

        else:
            raise TypeError("bitarray indices must be integers or slices, "
                            "not %s" % type(item).__name__)

    def __contains__(self, a):
        if isinstance(a, int):
            check_bit(a)
            return self._find_bit(a, 0, self._nbits) >= 0

        if isinstance(a, bitarray):
            return self._find(a, 0, self._nbits) >= 0

        raise TypeError("bitarray or int expected, got %s" % type(a).__name__)

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
    if not isinstance(s, str):
        raise TypeError
    default_endian = endian_from_string(s)
