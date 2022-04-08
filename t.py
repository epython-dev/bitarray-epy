from bitarray import bitarray

a = bitarray(endian='little')
print(a)
print(a.endian())
a.frombytes(b'A')
print(a)
del a[4:]
print(a)
print(a.tolist())
a.reverse()
print(a)
