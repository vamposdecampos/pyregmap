import unittest
import copy

class Register(object):
	def __init__(self, name, bit_length=None, defs=[]):
		if defs:
			if bit_length is not None:
				raise ValueError("cannot have both bit_length and sub-register definitions")
			bit_length = sum((reg._bit_length for reg in defs))
		self._name = name
		self._bit_length = bit_length
		self._defs = defs
		for reg in self._defs:
			setattr(self, reg._name, reg)

	def _set_bit_offset(self, bit_offset):
		self._bit_offset = bit_offset
		for reg in self._defs:
			bit_offset += reg._set_bit_offset(bit_offset)
		return self._bit_length

	def __call__(self, backend=None):
		"""Instantiate the register map"""
		res = copy.deepcopy(self)
		res._set_bit_offset(0)
		return res


class RegisterMapTest(unittest.TestCase):
	def setUp(self):
		self.TestMap = Register("test", defs = [
			Register("reg1", defs = [
				Register("field1", 4),
				Register("field2", 8),
			]),
			Register("reg2", defs = [
				Register("flag0", 1),
				Register("flag1", 1),
				Register("flag2", 1),
				Register("flag3", 1),
			]),
		])

	def test_layout(self):
		m = self.TestMap()
		self.assertEqual(m.reg1._bit_offset, 0)
		self.assertEqual(m.reg1._bit_length, 12)
		self.assertEqual(m.reg2._bit_offset, 12)
		self.assertEqual(m.reg2._bit_length, 4)
		self.assertEqual(m._bit_length, 16)
		self.assertEqual(m.reg1.field1._bit_offset, 0)
		self.assertEqual(m.reg1.field1._bit_length, 4)
		self.assertEqual(m.reg1.field2._bit_offset, 4)
		self.assertEqual(m.reg1.field2._bit_length, 8)
		self.assertEqual(m.reg2.flag0._bit_offset, 12)
		self.assertEqual(m.reg2.flag1._bit_offset, 13)
		self.assertEqual(m.reg2.flag2._bit_offset, 14)
		self.assertEqual(m.reg2.flag3._bit_offset, 15)
		self.assertEqual(m.reg2.flag0._bit_length, 1)
		self.assertEqual(m.reg2.flag1._bit_length, 1)
		self.assertEqual(m.reg2.flag2._bit_length, 1)
		self.assertEqual(m.reg2.flag3._bit_length, 1)

	def test_access(self):
		be = IntBackend()
		m = self.TestMap(be)
		m.reg1.field1._set(15)
		self.assertEqual(be.value, 15)


if __name__ == "__main__":
	unittest.main()
