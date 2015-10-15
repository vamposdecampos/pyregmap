import unittest

class Magic(object):
	"""Magic accessors for a Register
	
	For convenience, can be used to replace
		reg.foo.bar.baz._set(42)
		print reg.foo.bar.baz._get()
	with
		Magic(reg).foo.bar.baz = 42
		print Magic(reg).foo.bar.baz
	"""
	def __init__(self, reg):
		self._reg = reg
	def __getattr__(self, attr):
		sub = getattr(self._reg, attr)
		if sub._defs:
			return Magic(sub)
		else:
			return sub._get()
	def __setattr__(self, attr, value):
		if attr.startswith('_'):
			self.__dict__[attr] = value
			return
		sub = getattr(self._reg, attr)
		return sub._set(value)
	def __dir__(self):
		return dir(self._reg)

class Register(object):
	"""A register definition"""
	def __init__(self, name, bit_length=None, defs=[], rel_bitpos=None):
		if defs:
			sub_length = sum((reg._bit_length for reg in defs))
			if bit_length is not None:
				if bit_length < sub_length:
					raise ValueError("sum of sub-register lengths %d exceeds bit_length %d" % (sub_length, bit_length))
				if bit_length > sub_length:
					defs.append(RegUnused("_unused", bit_length - sub_length))
			else:
				bit_length = sub_length
		self._name = name
		self._bit_length = bit_length
		self._defs = defs
		self._rel_bitpos = rel_bitpos
		last_rel = 0
		padding = []
		for k, reg in enumerate(self._defs):
			assert not hasattr(self, reg._name)
			setattr(self, reg._name, reg)
			if reg._rel_bitpos is not None:
				delta = reg._rel_bitpos - last_rel
				if delta < 0:
					raise ValueError("register %r wants relative bit-position in the past (%d)" % (reg._name, delta))
				if delta:
					padding.append((k, RegUnused(
						"_unused_%d_%d" % (last_rel, reg._rel_bitpos),
						delta)))
				last_rel += delta
			last_rel += reg._bit_length
		for k, reg in reversed(padding):
			self._defs.insert(k, reg)

	def __call__(self, backend=None, bit_offset=0, magic=True):
		"""Instantiate the register map"""
		res = self.Instance(self, backend, bit_offset)
		return res._magic() if magic else res

class RegisterInstance(object):
	"""An instantiated register.  It has a backend and a well-defined bit position within it."""
	def __init__(self, reg, backend, bit_offset):
		self._reg = reg
		self._backend = backend
		self._bit_offset = bit_offset
		self._defs = []
		for reg in self._reg._defs:
			inst = reg(backend, bit_offset, magic=False)
			self._defs.append(inst)
			assert not hasattr(self, reg._name), "sub-register %r already defined" % reg._name
			setattr(self, reg._name, inst)
			bit_offset += inst._bit_length

	@property
	def _bit_length(self):
		return self._reg._bit_length
	@property
	def _name(self):
		return self._reg._name

	def _set(self, value):
		max = (1 << self._bit_length) - 1
		if value < 0 or value > max:
			raise ValueError('value %r out of 0..%i range' % (value, max))
		self._backend.set_bits(self._bit_offset, self._bit_length, value)
	def _get(self):
		return self._backend.get_bits(self._bit_offset, self._bit_length)
	def _magic(self):
		return Magic(self)
	def _getall(self):
		# TODO: caching, etc.
		if len(self._defs):
			return dict((reg._reg._name, reg._getall()) for reg in self._defs)
		else:
			return self._get()

Register.Instance = RegisterInstance


class RegRO(Register):
	"""A read-only register"""
	class Instance(RegisterInstance):
		def _set(self, value):
			raise TypeError("read-only register %r" % self._name)

class RegWO(Register):
	"""A write-only register"""
	class Instance(RegisterInstance):
		def _get(self):
			raise TypeError("write-only register %r" % self._name)

class RegUnused(Register):
	"""An unused register"""
	pass


class Backend(object):
	# TODO: @abc.abstractmethod?
	def set_bits(self, start, length, value):
		raise NotImplemented()
	def get_bits(self, start, length):
		raise NotImplemented()

class IntBackend(Backend):
	"""A backend backed by a (large) integer."""
	def __init__(self, value=0):
		self.value = value
	def set_bits(self, start, length, value):
		mask = (1 << length) - 1
		value &= mask
		self.value = (self.value & ~(mask << start)) | (value << start)
	def get_bits(self, start, length):
		mask = (1 << length) - 1
		return (self.value >> start) & mask

class GranularBackend(Backend):
	"""A backend which has a (lower) limit on granularity.
	
	For example, one cannot write less than 32 bits at a time; as such,
	writing a single bit may mean a read-modify-write cycle,  or it may
	be forbidden.
	"""
	granularity = 32 # bits

	def __init__(self, backend):
		self.backend = backend
	
	def compute_region(self, start, length):
		"""Return [start, end) boundaries required for accessing the underlying backend"""
		real_start = start - (start % self.granularity)
		real_end = start + length
		frag = real_end % self.granularity
		if frag:
			real_end += self.granularity - frag
		return (real_start, real_end)
	def compute_mask(self, start, length):
		rstart, rend = self.compute_region(start, length)
		rlen = rend - rstart
		mask = (1 << length) - 1
		delta = start - rstart
		return rstart, rlen, delta, mask
	def set_bits(self, start, length, value):
		rstart, rlen, delta, mask = self.compute_mask(start, length)
		if rstart < start or rlen > length:
			data = self.backend.get_bits(rstart, rlen)
		else:
			data = 0
		data = data & ~(mask << delta) | (value << delta)
		self.backend.set_bits(rstart, rlen, data)
	def get_bits(self, start, length):
		rstart, rlen, delta, mask = self.compute_mask(start, length)
		data = self.backend.get_bits(rstart, rlen)
		return (data >> delta) & mask

class BackendRecorder(Backend):
	GET = "get"
	SET = "set"

	def __init__(self, backend):
		self.backend = backend
		self.log = []
	def pop(self):
		return self.log.pop(0)
	def pop_nodata(self):
		return self.log.pop(0)[:-1]
	def empty(self):
		return not len(self.log)
	def get_bits(self, start, length):
		data = self.backend.get_bits(start, length)
		self.log.append((self.GET, start, length, data))
		return data
	def set_bits(self, start, length, value):
		self.log.append((self.SET, start, length, value))
		return self.backend.set_bits(start, length, value)

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
			Register("reg32", 16, rel_bitpos=8 * 0x32, defs=[
				RegRO("status0", 1),
				Register("cmd1", 1, rel_bitpos = 4),
				RegRO("status1", 1),
				RegRO("status2", 1),
				RegRO("status3", 1),
				Register("flag", 1, rel_bitpos = 14),
			]),
		])

	def test_layout(self):
		m = self.TestMap(magic=False)
		self.assertEqual(m.reg1._bit_offset, 0)
		self.assertEqual(m.reg1._bit_length, 12)
		self.assertEqual(m.reg2._bit_offset, 12)
		self.assertEqual(m.reg2._bit_length, 4)
		self.assertEqual(m._bit_length, 32)
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
		self.assertEqual(m.reg32.status0._bit_offset, 0x32 * 8)
		self.assertEqual(m.reg32.status3._bit_offset, 0x32 * 8 + 7)
		self.assertEqual(m.reg32.flag._bit_offset, 0x32 * 8 + 14)

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

if __name__ == "__main__":
	unittest.main()
