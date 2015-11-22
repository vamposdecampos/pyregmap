"""
mmap()-based backend
"""

import unittest
import sys
import os
import mmap
import stat

class MmapBackend(object):
	"""A backend backed by a memory-mapped file or device."""
	def __init__(self, fname, size=None, offset=0):
		if hasattr(fname, 'fileno'):
			fd = fname.fileno()
			ours = False
		else:
			fd = os.open(fname, os.O_RDWR | os.O_SYNC)
			ours = True
		if size is None:
			st = os.fstat(fd)
			size = st[stat.ST_SIZE] - offset
		self.mm = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, 0, offset)
		if ours:
			os.close(fd)
	def set_bits(self, start, length, value):
		assert start % 8 == 0
		assert length % 8 == 0
		bstart = start / 8
		blen = length / 8
		bend = bstart + blen
		bytes = []
		for k in xrange(blen):
			bytes.append(value & 0xff)
			value >>= 8
		if sys.byteorder != 'little':
			bytes = reversed(bytes)
		self.mm[bstart:bend] = str(bytearray(bytes))
	def get_bits(self, start, length):
		assert start % 8 == 0
		assert length % 8 == 0
		bstart = start / 8
		blen = length / 8
		bend = bstart + blen
		value = 0
		bytes = bytearray(self.mm[bstart:bend])
		if sys.byteorder == 'little':
			bytes = reversed(bytes)
		for b in bytes:
			value <<= 8
			value |= b
		return value

class MmapTest(unittest.TestCase):
	def setUp(self):
		self.fp = os.tmpfile()
		self.fp.write('deadbeef'.decode('hex'))
		self.fp.flush()
	def test_read(self):
		be = MmapBackend(self.fp)
		self.assertEqual(be.get_bits(0, 8), 0xde)
		self.assertEqual(be.get_bits(0, 16), 0xadde)
		self.assertEqual(be.get_bits(8, 16), 0xbead)
		self.assertEqual(be.get_bits(0, 32), 0xefbeadde)
	def test_write(self):
		be = MmapBackend(self.fp)
		be.set_bits(8, 16, 0x55aa)
		self.fp.seek(0)
		self.assertEqual(self.fp.read(4).encode('hex'), 'deaa55ef')

if __name__ == "__main__":
	unittest.main()
