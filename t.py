from bitarray import bitarray

a = bitarray('1100111')
print(len(a))
print(a.endian())
print(a.find(bitarray('01'), 3))
