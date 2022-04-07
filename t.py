from bitarray import bitarray

a = bitarray('110')
print(len(a))
print(a.endian())
print(a)
a.reverse()
print(a)
print(a.count())
del a[1]
print(a)
