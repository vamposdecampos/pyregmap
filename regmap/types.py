import unittest


class RegisterMap(object):
	pass


class RegisterMapTest(unittest.TestCase):
	def test_layout(self):
		class TestMap(RegisterMap):
			pass

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
