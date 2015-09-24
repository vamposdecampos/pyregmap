import unittest


class Register(object):
	def __init__(self, name, bit_length=None, defs=[]):
		self._name = name
		self._bit_length = bit_length
		self._defs = defs
		for reg in self._defs:
			setattr(self, reg._name, reg)

	def __call__(self, backend=None):
		"""Instantiate the register map"""
		# TODO
		return self


class RegisterMapTest(unittest.TestCase):
	def test_layout(self):
		TestMap = Register("test", defs = [
			Register("reg1", defs = [
				Register("field1", 4),
				Register("field2", 8),
			]),
			Register("reg2", defs = [
				Register("flag0"),
				Register("flag1"),
				Register("flag2"),
				Register("flag3"),
			]),
		])

		m = TestMap()
		self.assertEqual(m.reg1._bit_offset, 0)
		self.assertEqual(m.reg1._bit_length, 12)
		self.assertEqual(m.reg2._bit_offset, 12)
		self.assertEqual(m.reg2._bit_length, 4)
		self.assertEqual(m._bit_length, 16)
		self.assertEqual(m.reg1.field1._bit_offset, 0)
		self.assertEqual(m.reg1.field1._bit_length, 4)
		self.assertEqual(m.reg1.field2._bit_offset, 4)
		self.assertEqual(m.reg1.field2._bit_length, 8)
		self.assertEqual(m.reg2.flag0._bit_offset, 8)
		self.assertEqual(m.reg2.flag1._bit_offset, 9)
		self.assertEqual(m.reg2.flag2._bit_offset, 10)
		self.assertEqual(m.reg2.flag3._bit_offset, 11)
		self.assertEqual(m.reg2.flag0._bit_length, 1)
		self.assertEqual(m.reg2.flag1._bit_length, 1)
		self.assertEqual(m.reg2.flag2._bit_length, 1)
		self.assertEqual(m.reg2.flag3._bit_length, 1)

if __name__ == "__main__":
	unittest.main()
