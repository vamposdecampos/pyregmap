from .types import Backend
import unittest

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
	def begin_update(self, start, length, mode):
		rstart, rlen, delta, mask = self.compute_mask(start, length)
		return self.backend.begin_update(rstart, rlen, mode)
	def end_update(self, start, length, mode):
		rstart, rlen, delta, mask = self.compute_mask(start, length)
		return self.backend.end_update(rstart, rlen, mode)


class WindowBackend(Backend):
	"""A backend wrapper that can translate accesses to a different bit offset."""
	def __init__(self, backend, offset=0):
		self.backend = backend
		self.offset = offset
	def set_bits(self, start, length, value):
		return self.backend.set_bits(self.offset + start, length, value)
	def get_bits(self, start, length):
		return self.backend.get_bits(self.offset + start, length)
	def begin_update(self, start, length, mode):
		return self.backend.begin_update(self.offset + start, length)
	def end_update(self, start, length, mode):
		return self.backend.end_update(self.offset + start, length)

class CachingBackend(Backend):
	"""A caching wrapper around another backend."""

	class CachedAccess(object):
		def __init__(self, backend, start, length, mode):
			self.start = start
			self.length = length
			self.mode = mode
			self.real_backend = backend
			self.backend = WindowBackend(IntBackend(), -start)
			if self.mode != Backend.MODE_WRITE:
				self.backend.set_bits(start, length, backend.get_bits(start, length))
			self.written = WindowBackend(IntBackend(), -start)
		def set_bits(self, start, length, value):
			if self.mode == Backend.MODE_READ:
				raise ValueError("read-only cache access tried to set bits")
			self.written.set_bits(start, length, (1 << length) - 1)
			return self.backend.set_bits(start, length, value)
		def get_bits(self, start, length):
			if self.mode == Backend.MODE_WRITE:
				raise ValueError("write-only cache access tried to get bits")
			return self.backend.get_bits(start, length)

	def __init__(self, backend):
		self.backend = backend
		self.cache = [backend]

	def begin_update(self, start, length, mode):
		self.cache.append(self.CachedAccess(self.backend, start, length, mode))
	def end_update(self, start, length, mode):
		assert len(self.cache) > 1
		acc = self.cache.pop()
		if mode == Backend.MODE_DISCARD:
			return
		# 'with' statements must be properly nested, if at all:
		assert acc.start == start
		assert acc.length == length
		assert acc.mode == mode
		mask = acc.written.get_bits(start, length)
		full = (1 << length) - 1
		if mode == Backend.MODE_WRITE:
			if mask != full:
				raise ValueError("write-only cached access did not set all bits (0x%x missing)" % (full ^ mask))
		if mask:
			assert mode != Backend.MODE_READ # should be caught earlier
			self.backend.set_bits(start, length, acc.backend.get_bits(start, length))
		# TODO: may require reloading the next top of cache, or merging
		assert len(self.cache) == 1, "nested cached 'with' statements not yet supported"

	def set_bits(self, start, length, value):
		return self.cache[-1].set_bits(start, length, value)
	def get_bits(self, start, length):
		return self.cache[-1].get_bits(start, length)


class BackendRecorder(Backend):
	GET = "get"
	SET = "set"
	BEGIN = "begin"
	END = "end"

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
	def begin_update(self, start, length, mode):
		self.log.append((self.BEGIN, start, length, mode))
		return self.backend.begin_update(start, length, mode)
	def end_update(self, start, length, mode):
		self.log.append((self.END, start, length, mode))
		return self.backend.begin_update(start, length, mode)
