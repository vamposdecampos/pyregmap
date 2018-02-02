import sys

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
	def __enter__(self):
		return self._reg.__enter__()
	def __exit__(self, type, value, traceback):
		return self._reg.__exit__(type, value, traceback)

def named_int_factory(reg, base=int):
	return type("enum.%s" % reg._name, (base,), dict(
		__str__	= lambda self: reg._enum_i2h.get(self, base.__str__(self)),
		__repr__= lambda self: reg._enum_i2h.get(self, base.__repr__(self)),
	))

class Modifier(object):
	"""An meta-register that acts upon other registers in a definition list"""
	@staticmethod
	def modify_defs(lst):
		mod = None
		for item in lst:
			if isinstance(item, Modifier):
				mod = item
				continue
			if mod is not None:
				mod, item = mod.modify(item)
			if item is not None:
				yield item
	def modify(self, item):
		raise NotImplemented

class AtBit(Modifier):
	"""Make the next Register start at the given rel_bitpos"""
	def __init__(self, bit):
		self.bit = bit
	def modify(self, reg):
		reg._rel_bitpos = self.bit
		return None, reg

class AtByte(AtBit):
	"""Make the next Register start at a rel_bitpos, given in bytes"""
	def __init__(self, byte):
		super(AtByte, self).__init__(8 * byte)


class Register(object):
	"""A register definition"""

	# if not None, @unused indicates the default value we write
	# to the register if we've never read it.
	_unused = None

	def __init__(self, name, bit_length=None, defs=[], rel_bitpos=None, enum={}, doc=None):
		defs = list(Modifier.modify_defs(defs))
		if defs and (bit_length is not None):
			sub_length = sum((reg._bit_length for reg in defs))
			if bit_length < sub_length:
				raise ValueError("sum of sub-register lengths %d exceeds bit_length %d" % (sub_length, bit_length))
		if type(enum) != dict:
			enum = dict(enumerate(enum))
		self._name = name
		self._defs = defs
		self._doc = doc
		self._rel_bitpos = rel_bitpos
		self._enum_i2h = enum
		self._enum_h2i = dict(((v, k) for k, v in enum.iteritems()))
		# TODO: sanity-check that enum values don't overlap
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
					padding.append((k, RegRAZ(
						"_unused_%d_%d" % (last_rel, reg._rel_bitpos),
						delta)))
				last_rel += delta
			last_rel += reg._bit_length
		for k, reg in reversed(padding):
			self._defs.insert(k, reg)
		if self._defs:
			if bit_length is None:
				bit_length = last_rel
			elif bit_length > last_rel:
				self._defs.append(RegRAZ(
					"_unused_%d_%d" % (last_rel, bit_length),
					bit_length - last_rel))
		self._bit_length = bit_length

	def __call__(self, backend=None, bit_offset=0, parent=None, magic=False, automagic=None):
		"""Instantiate the register map"""
		if automagic is None:
			automagic = magic
		res = self.Instance(self, backend, bit_offset, parent, automagic=automagic)
		return res._magic(True) if magic else res

class RegisterInstance(object):
	"""An instantiated register.  It has a backend and a well-defined bit position within it."""
	def __init__(self, reg, backend, bit_offset, parent, automagic=False):
		self._reg = reg
		self._backend = backend
		self._bit_offset = bit_offset
		self._defs = []
		self._parent = parent
		self._automagic = automagic
		if parent:
			self._long_name = '%s.%s' % (self._parent._long_name, self._name)
		else:
			self._long_name = self._name
		for reg in self._reg._defs:
			inst = reg(backend, bit_offset, magic=False, parent=self, automagic=self._automagic)
			self._defs.append(inst)
			assert not hasattr(self, reg._name), "sub-register %r already defined" % reg._name
			setattr(self, reg._name, inst)
			bit_offset += inst._bit_length
	def __repr__(self):
		return "<%s %s>" % (self._reg.__class__.__name__, self._long_name)

	@property
	def _bit_length(self):
		return self._reg._bit_length
	@property
	def _name(self):
		return self._reg._name

	def __call__(self, value=None):
		"_set() if called with an argument, _get() otherwise"
		if value is None:
			return self._get()
		return self._set(value)

	def _set(self, value):
		if type(value) != int:
			value = self._h2i(value)
		max = (1 << self._bit_length) - 1
		if value < 0 or value > max:
			raise ValueError('value %r out of 0..%i range' % (value, max))
		self._backend.set_bits(self._bit_offset, self._bit_length, value)
	def _get(self):
		value = self._backend.get_bits(self._bit_offset, self._bit_length)
		return self._i2h(value)
	def _magic(self, always=False):
		if always or self._automagic:
			return Magic(self)
		return self
	def _getall(self):
		# TODO: caching, etc.
		if len(self._defs):
			return dict((reg._reg._name, reg._getall()) for reg in self._defs)
		else:
			return self._get()

	def _i2h(self, value):
		"""Convert integer to human-readable value (if any)"""
		return named_int_factory(self._reg, int if value < sys.maxint else long)(value)
	def _h2i(self, value):
		"""Convert human-readable value to integer; raise ValueError if not possible."""
		try:
			return self._reg._enum_h2i[value]
		except KeyError:
			return int(value) # raises ValueError

	# like _set(), but allow "writing" of read-only fields.  internal only.
	_preset = _set

	def _preset_reserved(self):
		"""Write the values of reserved/unused sub-registers to the backend."""
		if self._reg._unused is not None:
			self._preset(self._reg._unused)
		for sub in self._defs:
			sub._preset_reserved()

	def _visit_regs(self, test_func):
		"""Recursively visit all sub-registers and call test_func(reg) on them.
		
		Return an iterator consisting of all such registers where the function
		returned True"""
		if not len(self._defs):
			if test_func(self):
				yield self
			return
		for sub in self._defs:
			for res in sub._visit_regs(test_func):
				yield res
	def _find_regs(self, bit_offset, bit_length):
		"""Return all registers that fit in the specified bit interval."""
		return self._visit_regs(lambda r: not (\
				(bit_offset + bit_length <= r._bit_offset) or \
				(bit_offset >= r._bit_offset + r._bit_length)))
	def _find_reg(self, bit_offset):
		for reg in self._visit_regs(lambda r: \
				r._bit_offset <= bit_offset < (r._bit_offset + r._bit_length)):
			return reg


	def __enter__(self):
		self._backend.begin_update(self._bit_offset, self._bit_length, Backend.MODE_RMW)
		return self._magic()
	def __exit__(self, type, value, traceback):
		self._backend.end_update(self._bit_offset, self._bit_length, Backend.MODE_RMW)

Register.Instance = RegisterInstance


class RegRO(Register):
	"""A read-only register"""
	_unused = 0
	class Instance(RegisterInstance):
		def _set(self, value):
			raise TypeError("read-only register %r" % self._name)

class RegWO(Register):
	"""A write-only register"""
	class Instance(RegisterInstance):
		def _get(self):
			raise TypeError("write-only register %r" % self._name)
		def _getall(self):
			return None

class RegRAZ(Register):
	"""A reserved read-as-zero register."""
	_unused = 0



class Backend(object):
	"""An abstract backend"""

	MODE_RMW	= 'rmw'
	MODE_READ	= 'read'
	MODE_WRITE	= 'write'
	MODE_DISCARD	= 'discard' # exception raised, skip the writeback

	# TODO: @abc.abstractmethod?
	def set_bits(self, start, length, value):
		raise NotImplemented()
	def get_bits(self, start, length):
		raise NotImplemented()
	def begin_update(self, start, length, mode):
		pass # nop
	def end_update(self, start, length, mode):
		pass # nop

class rmw_access(object):
	mode = Backend.MODE_RMW
	def __init__(self, reg):
		if isinstance(reg, Magic):
			reg = reg._reg
		self.reg = reg
	def __enter__(self):
		self.reg._backend.begin_update(self.reg._bit_offset, self.reg._bit_length, self.mode)
		return self.reg._magic()
	def __exit__(self, type, value, traceback):
		self.reg._backend.end_update(self.reg._bit_offset, self.reg._bit_length,
			self.mode if traceback is None else Backend.MODE_DISCARD)

class read_access(rmw_access):
	mode = Backend.MODE_READ

class write_access(rmw_access):
	mode = Backend.MODE_WRITE
	def __enter__(self):
		res = super(write_access, self).__enter__()
		self.reg._preset_reserved()
		return res
