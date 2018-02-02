import unittest
from .types import *
from .backends import *

class BaseTestCase(unittest.TestCase):
	def setUp(self):
		self.TestMap = Register("test", defs = [
			Register("reg1", defs = [
				Register("field1", 4),
				Register("field2", 8),
			]),
			Register("reg2", defs = [
				Register("flag0", 1),
				Register("flag1", 1),
				Register("flag2", 1, enum=("no", "yes")),
				Register("flag3", 1),
			]),
			Register("reg32", 16, rel_bitpos=8 * 0x32, defs=[
				RegRO("status0", 1),
				RegWO("cmd1", 1, rel_bitpos = 4),
				RegRO("status1", 1),
				RegRO("status2", 1),
				RegRO("status3", 1),
				Register("flag", 1, rel_bitpos = 14),
			]),
		])

class SparseTestCase(unittest.TestCase):
	def setUp(self):
		self.TestMap = Register("test", defs = [
			Register("reg1", defs = [
				Register("field1", 4),
				Register("field2", 8),
			]),
			Register("reg2", defs = [
				Register("flag0", 1),
				Register("flag1", 1),
				Register("flag2", 1, enum=("no", "yes")),
				Register("flag3", 1),
			]),
			AtByte(0x32),
			Register("reg32", 16, defs=[
				RegRO("status0", 1),
				AtBit(4),
				RegWO("cmd1", 1),
				RegRO("status1", 1),
				RegRO("status2", 1),
				RegRO("status3", 1),
				AtBit(14),
				Register("flag", 1),
			]),
		])

class LayoutTestCase(object):
	def test_layout(self):
		m = self.TestMap(magic=False)
		self.assertEqual(m.reg1._bit_offset, 0)
		self.assertEqual(m.reg1._bit_length, 12)
		self.assertEqual(m.reg2._bit_offset, 12)
		self.assertEqual(m.reg2._bit_length, 4)
		self.assertEqual(m._bit_length, 8 * 0x32 + 16)
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
		self.assertEqual(m.reg32._bit_offset, 0x32 * 8)
		self.assertEqual(m.reg32.status0._bit_offset, 0x32 * 8)
		self.assertEqual(m.reg32.status3._bit_offset, 0x32 * 8 + 7)
		self.assertEqual(m.reg32.flag._bit_offset, 0x32 * 8 + 14)
		self.assertEqual(sum((x._bit_length for x in m.reg1._defs)), 12)
		self.assertEqual(sum((x._bit_length for x in m.reg32._defs)), 16)

class ClassicLayoutTestCase(BaseTestCase, LayoutTestCase):
	pass

class SparseLayoutTestCase(SparseTestCase, LayoutTestCase):
	pass

class RegisterMapTest(BaseTestCase):
	def test_reverse_lookup(self):
		m = self.TestMap(magic=False)
		self.assertEqual(m._find_reg(15), m.reg2.flag3)
		self.assertEqual(set(m._find_regs(15, 1)), set([m.reg2.flag3]))
		self.assertEqual(set(m._find_regs(14, 2)), set([m.reg2.flag2, m.reg2.flag3]))

	def test_cosmetic(self):
		m = self.TestMap(magic=False)
		self.assertEqual(repr(m.reg2.flag3), '<Register test.reg2.flag3>')

	def test_access(self):
		be = IntBackend()
		m = self.TestMap(be, magic=False)
		m.reg1.field1._set(15)
		self.assertEqual(be.value, 15)
		self.assertEqual(m.reg1.field1._get(), 15)
		be.value = 0x55aa
		self.assertEqual(m.reg1.field1._get(), 10)
		self.assertEqual(m.reg1.field2._get(), 0x5a)
		self.assertEqual(m.reg1._get(), 0x5aa)
		self.assertEqual(m.reg2._get(), 0x5)
		self.assertTrue(m.reg2.flag0._get())
		self.assertFalse(m.reg2.flag1._get())
		self.assertTrue(m.reg2.flag2._get())
		self.assertEqual(m.reg2.flag2._get(), 1)
		self.assertEqual(str(m.reg2.flag2._get()), 'yes')
		self.assertFalse(m.reg2.flag3._get())
		with self.assertRaises(ValueError):
			m.reg1._set(-1)
		with self.assertRaises(ValueError):
			m.reg1._set(0x1000)

	def test_magic(self):
		be = IntBackend()
		m = self.TestMap(be)
		self.assertEqual(m.reg1.field1, 0)
		m.reg2.flag2 = 1
		self.assertEquals(be.value, 0x4000)
		self.assertEqual(m.reg2._reg._get(), 4)
		m.reg2.flag2 = 'no'
		self.assertEqual(m.reg2._reg._get(), 0)
		m.reg2.flag2 = 'yes'
		self.assertEqual(m.reg2._reg._get(), 4)

	def test_no_magic(self):
		be = IntBackend()
		m = self.TestMap(be, magic=False)
		self.assertEqual(m.reg1.field1(), 0)
		m.reg2.flag2(1)
		self.assertEquals(be.value, 0x4000)
		self.assertEqual(m.reg2(), 4)
		m.reg2.flag2('no')
		self.assertEqual(m.reg2(), 0)
		m.reg2.flag2('yes')
		self.assertEqual(m.reg2(), 4)

	def test_nested(self):
		be = IntBackend()
		n = Register("nested", defs = [
			Register("one", defs=self.TestMap._defs),
			Register("two", defs=self.TestMap._defs),
		])(be)
		self.assertEqual(n.one.reg1.field1, 0)
		n.one.reg1.field1 = 7
		n.two.reg1.field1 = 1
		self.assertEqual(n.one.reg1.field1, 7)
		self.assertEqual(n.two.reg1.field1, 1)

	def test_getall(self):
		m = self.TestMap(IntBackend(), magic=False)
		self.assertEqual(m.reg32._getall(), {
			'_unused_15_16': 0,
			'_unused_1_4': 0,
			'_unused_8_14': 0,
			'cmd1': None,
			'flag': 0,
			'status0': 0,
			'status1': 0,
			'status2': 0,
			'status3': 0,
		})

	def test_granular_region(self):
		gb = GranularBackend(IntBackend())
		self.assertEqual(gb.compute_region(0, 32), (0, 32))
		self.assertEqual(gb.compute_region(5, 1), (0, 32))
		self.assertEqual(gb.compute_region(31, 1), (0, 32))
		self.assertEqual(gb.compute_region(31, 2), (0, 64))
		self.assertEqual(gb.compute_region(32, 1), (32, 64))

	def test_granular_access(self):
		rec = BackendRecorder(IntBackend())
		gb = GranularBackend(rec)
		gb.set_bits(0, 32, 0xdeadbeef)
		self.assertEqual(rec.pop(), (rec.SET, 0, 32, 0xdeadbeef))
		self.assertTrue(rec.empty())
		gb.set_bits(16, 32, 0xcafebabe)
		self.assertEqual(rec.pop(), (rec.GET, 0, 64, 0xdeadbeef))
		self.assertEqual(rec.pop(), (rec.SET, 0, 64, 0xcafebabebeef))
		self.assertTrue(rec.empty())
		self.assertEqual(gb.get_bits(24, 8), 0xba)
		self.assertEqual(rec.pop(), (rec.GET, 0, 32, 0xbabebeef))
		self.assertTrue(rec.empty())

	def test_int_bits(self):
		m = Register("test", defs = [
			Register("reg128", 128),
		])(IntBackend(), magic=False)
		m.reg128._set(0xec000002 << 64)
		self.assertEqual(m.reg128._get(), 0xec000002 << 64)

class ContextManagerTest(BaseTestCase):
	def setUp(self):
		super(ContextManagerTest, self).setUp()
		self.rec = BackendRecorder(IntBackend())
		self.gb = GranularBackend(self.rec)
		self.cb = CachingBackend(self.gb)
	def test_context_manager(self):
		rec = self.rec
		m = self.TestMap(self.gb, magic=False)
		with m.reg1 as reg:
			self.assertEqual(rec.pop(), (rec.BEGIN, 0, 32, Backend.MODE_RMW))
			self.assertEqual(reg.field1, 0)
			self.assertEqual(rec.pop(), (rec.GET, 0, 32, 0))
			self.assertEqual(reg.field2, 0)
			self.assertEqual(rec.pop(), (rec.GET, 0, 32, 0))
			reg.field2 = 5
			self.assertEqual(rec.pop(), (rec.GET, 0, 32, 0))
			self.assertEqual(rec.pop(), (rec.SET, 0, 32, 80))
			self.assertEqual(reg.field2, 5)
			self.assertEqual(rec.pop(), (rec.GET, 0, 32, 80))
		self.assertEqual(rec.pop(), (rec.END, 0, 32, Backend.MODE_RMW))
		self.assertTrue(rec.empty())

	def test_context_manager_mode(self):
		rec = self.rec
		m = self.TestMap(rec, magic=False)
		with rmw_access(m.reg1) as reg:
			self.assertEqual(rec.pop(), (rec.BEGIN, 0, 12, Backend.MODE_RMW))
		self.assertEqual(rec.pop(), (rec.END, 0, 12, Backend.MODE_RMW))
		self.assertTrue(rec.empty())
		with read_access(m.reg1) as reg:
			self.assertEqual(rec.pop(), (rec.BEGIN, 0, 12, Backend.MODE_READ))
		self.assertEqual(rec.pop(), (rec.END, 0, 12, Backend.MODE_READ))
		self.assertTrue(rec.empty())
		with write_access(m.reg1) as reg:
			self.assertEqual(rec.pop(), (rec.BEGIN, 0, 12, Backend.MODE_WRITE))
		self.assertEqual(rec.pop(), (rec.END, 0, 12, Backend.MODE_WRITE))
		self.assertTrue(rec.empty())

	def test_context_manager_cache(self):
		rec = self.rec
		m = self.TestMap(self.cb, magic=False)
		# automagic RMW
		with m.reg1 as reg:
			self.assertEqual(rec.pop(), (rec.GET, 0, 32, 0))
			self.assertEqual(reg.field1, 0)
			self.assertEqual(reg.field2, 0)
			reg.field1 = 1
			self.assertEqual(reg.field1, 1)
			self.assertEqual(reg.field2, 0)
			reg.field2 = 5
			self.assertEqual(reg.field1, 1)
			self.assertEqual(reg.field2, 5)
			self.assertTrue(rec.empty())
		self.assertEqual(rec.pop(), (rec.GET, 0, 32, 0))
		self.assertEqual(rec.pop(), (rec.SET, 0, 32, 81))
		self.assertTrue(rec.empty())
		# automagic read-only
		with m.reg1 as reg:
			self.assertEqual(rec.pop(), (rec.GET, 0, 32, 81))
			self.assertEqual(reg.field1, 1)
			self.assertEqual(reg.field2, 5)
		self.assertTrue(rec.empty())
		# non-cached access
		self.assertEqual(m.reg1.field2._get(), 5)
		m.reg1.field2._set(1)
		self.assertEqual(m.reg1.field2._get(), 1)

	def test_readonly_write(self):
		rec = self.rec
		m = self.TestMap(self.cb, magic=False)
		with read_access(m.reg1) as reg:
			with self.assertRaisesRegexp(ValueError, "tried to set"):
				reg.field1 = 0
		self.assertEqual(rec.pop(), (rec.GET, 0, 32, 0))
		self.assertTrue(rec.empty())

	def test_writeonly_incomplete(self):
		rec = self.rec
		m = self.TestMap(self.cb, magic=False)
		with self.assertRaisesRegexp(ValueError, "did not set all bits"):
			with write_access(m.reg1) as reg:
				pass
		self.assertTrue(rec.empty())

	def test_context_mgr_write_only(self):
		rec = self.rec
		m = self.TestMap(self.cb, magic=False)
		self.gb.granularity = 1
		with write_access(m.reg2) as reg:
			self.assertTrue(rec.empty())
			reg.flag0 = 1
			reg.flag1 = 0
			reg.flag2 = 'yes'
			reg.flag3 = 0
		self.assertEqual(rec.pop(), (rec.SET, 12, 4, 1 | 4))
		self.assertTrue(rec.empty())

	def test_context_mgr_write_only_sparse(self):
		rec = self.rec
		m = self.TestMap(self.cb, magic=False)
		self.gb.granularity = 16
		with write_access(m.reg32) as reg:
			self.assertTrue(rec.empty())
			reg.cmd1 = 1
			reg.flag = 0
		self.assertEqual(rec.pop(), (rec.SET, 8 * 0x32, 16, 0x10))
		self.assertTrue(rec.empty())

if __name__ == "__main__":
	unittest.main()
