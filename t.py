from bitarray import bitarray, _set_default_endian
from bitarray.test_bitarray import Util

class X(Util):

    def test(self):
        for lst in self.randomlists():
            a = bitarray(lst)
            if a.tolist() != lst:
                print(lst)
                print(a)
                return

"""
x = X()
x.test()

tup = 0, 1, 0
print(hasattr(tup, '__iter__'))
a = bitarray(tup)
print(a)
a.extend(tup)
print(a)
"""
_set_default_endian(0)
