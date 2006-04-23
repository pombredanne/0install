#!/usr/bin/env python2.3
import sys, tempfile, os, shutil, sha
import unittest

sys.path.insert(0, '..')
from zeroinstall.zerostore import unpack, manifest
from zeroinstall import SafeException

class TestUnpack(unittest.TestCase):
	def setUp(self):
		self.tmpdir = tempfile.mkdtemp('-testunpack')
	
	def tearDown(self):
		shutil.rmtree(self.tmpdir)
	
	def testBadExt(self):
		try:
			unpack.unpack_archive('ftp://foo/file.foo', file('HelloWorld.tgz'), self.tmpdir)
			assert False
		except SafeException, ex:
			assert 'Unknown extension' in str(ex)
	
	def testTgz(self):
		unpack.unpack_archive('ftp://foo/file.tgz', file('HelloWorld.tgz'), self.tmpdir)
		self.assert_manifest('sha1=3ce644dc725f1d21cfcf02562c76f375944b266a')
	
	def testExtract(self):
		unpack.unpack_archive('ftp://foo/file.tgz', file('HelloWorld.tgz'), self.tmpdir, extract = 'HelloWorld')
		self.assert_manifest('sha1=3ce644dc725f1d21cfcf02562c76f375944b266a')
	
	def testExtractIllegal(self):
		try:
			unpack.unpack_archive('ftp://foo/file.tgz', file('HelloWorld.tgz'), self.tmpdir, extract = 'Hello`World`')
			assert False
		except SafeException, ex:
			assert 'Illegal' in str(ex)
	
	def testExtractFails(self):
		stderr = os.dup(2)
		try:
			null = os.open('/dev/null', os.O_RDONLY)
			os.close(2)
			os.dup2(null, 2)
			try:
				unpack.unpack_archive('ftp://foo/file.tgz', file('HelloWorld.tgz'), self.tmpdir, extract = 'HelloWorld2')
				assert False
			except SafeException, ex:
				assert 'Failed to extract' in str(ex)
		finally:
			os.dup2(stderr, 2)
	
	def testTargz(self):
		unpack.unpack_archive('ftp://foo/file.tar.GZ', file('HelloWorld.tgz'), self.tmpdir)
		self.assert_manifest('sha1=3ce644dc725f1d21cfcf02562c76f375944b266a')
	
	def testTbz(self):
		unpack.unpack_archive('ftp://foo/file.tar.bz2', file('HelloWorld.tar.bz2'), self.tmpdir)
		self.assert_manifest('sha1=3ce644dc725f1d21cfcf02562c76f375944b266a')
	
	def testRPM(self):
		unpack.unpack_archive('ftp://foo/file.rpm', file('dummy-1-1.noarch.rpm'), self.tmpdir)
		self.assert_manifest('sha1=7be9228c8fe2a1434d4d448c4cf130e3c8a4f53d')
	
	def assert_manifest(self, required):
		sha1 = 'sha1=' + manifest.add_manifest_file(self.tmpdir, sha.new()).hexdigest()
		self.assertEquals(sha1, required)

suite = unittest.makeSuite(TestUnpack)
if __name__ == '__main__':
	sys.argv.append('-v')
	unittest.main()