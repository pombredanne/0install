"""Unpacking archives of various formats."""

# Copyright (C) 2009, Thomas Leonard
# See the README file for details, or visit http://0install.net.

from zeroinstall import _, logger
import os, sys, subprocess
import shutil
import glob
import traceback
from tempfile import mkdtemp, mkstemp
import re
import errno
from zeroinstall import SafeException
from zeroinstall.support import find_in_path, ro_rmtree

_cpio_version = None
def _get_cpio_version():
	global _cpio_version
	if _cpio_version is None:
		child = subprocess.Popen(['cpio', '--version'], stdout = subprocess.PIPE,
					stderr = subprocess.STDOUT, universal_newlines = True)
		out, unused = child.communicate()
		child.stdout.close()
		child.wait()
		_cpio_version = out.split('\n', 1)[0]
		logger.debug(_("cpio version = %s"), _cpio_version)
	return _cpio_version

def _gnu_cpio():
	gnu_cpio = '(GNU cpio)' in _get_cpio_version()
	logger.debug(_("Is GNU cpio = %s"), gnu_cpio)
	return gnu_cpio

_tar_version = None
def _get_tar_version():
	"""@rtype: str"""
	global _tar_version
	if _tar_version is None:
		child = subprocess.Popen(['tar', '--version'], stdout = subprocess.PIPE,
					stderr = subprocess.STDOUT, universal_newlines = True)
		out, unused = child.communicate()
		child.stdout.close()
		child.wait()
		_tar_version = out.split('\n', 1)[0]
		logger.debug(_("tar version = %s"), _tar_version)
	return _tar_version

def _gnu_tar():
	"""@rtype: bool"""
	gnu_tar = '(GNU tar)' in _get_tar_version()
	logger.debug(_("Is GNU tar = %s"), gnu_tar)
	return gnu_tar

# unicode compat
if sys.version_info < (3,):
	def _u(s):
		if isinstance(s, unicode): return s
		return s.decode('utf-8')
else:
	def _u(s): return s

def recent_gnu_tar():
	"""@rtype: bool
	@deprecated: should be private"""
	recent_gnu_tar = False
	if _gnu_tar():
		version = re.search(r'\)\s*(\d+(\.\d+)*)', _get_tar_version())
		if version:
			version = list(map(int, version.group(1).split('.')))
			recent_gnu_tar = version > [1, 13, 92]
		else:
			logger.warning(_("Failed to extract GNU tar version number"))
	logger.debug(_("Recent GNU tar = %s"), recent_gnu_tar)
	return recent_gnu_tar

# Disabled, as Plash does not currently support fchmod(2).
_pola_run = None
#_pola_run = find_in_path('pola-run')
#if _pola_run:
#	info('Found pola-run: %s', _pola_run)
#else:
#	info('pola-run not found; archive extraction will not be sandboxed')

def type_from_url(url):
	"""Guess the MIME type for this resource based on its URL. Returns None if we don't know what it is.
	@type url: str
	@rtype: str | None"""
	url = url.lower()
	if url.endswith('.rpm'): return 'application/x-rpm'
	if url.endswith('.deb'): return 'application/x-deb'
	if url.endswith('.tar.bz2'): return 'application/x-bzip-compressed-tar'
	if url.endswith('.tar.gz'): return 'application/x-compressed-tar'
	if url.endswith('.tar.lzma'): return 'application/x-lzma-compressed-tar'
	if url.endswith('.tar.xz'): return 'application/x-xz-compressed-tar'
	if url.endswith('.tbz'): return 'application/x-bzip-compressed-tar'
	if url.endswith('.tgz'): return 'application/x-compressed-tar'
	if url.endswith('.tlz'): return 'application/x-lzma-compressed-tar'
	if url.endswith('.txz'): return 'application/x-xz-compressed-tar'
	if url.endswith('.tar'): return 'application/x-tar'
	if url.endswith('.zip'): return 'application/zip'
	if url.endswith('.cab'): return 'application/vnd.ms-cab-compressed'
	if url.endswith('.dmg'): return 'application/x-apple-diskimage'
	if url.endswith('.gem'): return 'application/x-ruby-gem'
	return None

def check_type_ok(mime_type):
	"""Check we have the needed software to extract from an archive of the given type.
	@type mime_type: str
	@raise SafeException: if the needed software is not available"""
	assert mime_type
	if mime_type == 'application/x-rpm':
		if not find_in_path('rpm2cpio'):
			raise SafeException(_("This package looks like an RPM, but you don't have the rpm2cpio command "
					"I need to extract it. Install the 'rpm' package first (this works even if "
					"you're on a non-RPM-based distribution such as Debian)."))
	elif mime_type == 'application/x-deb':
		if not find_in_path('ar'):
			raise SafeException(_("This package looks like a Debian package, but you don't have the 'ar' command "
					"I need to extract it. Install the package containing it (sometimes called 'binutils') "
					"first. This works even if you're on a non-Debian-based distribution such as Red Hat)."))
	elif mime_type == 'application/x-bzip-compressed-tar':
		pass	# We'll fall back to Python's built-in tar.bz2 support
	elif mime_type == 'application/zip':
		if not find_in_path('unzip'):
			raise SafeException(_("This package looks like a zip-compressed archive, but you don't have the 'unzip' command "
					"I need to extract it. Install the package containing it first."))
	elif mime_type == 'application/vnd.ms-cab-compressed':
		if not find_in_path('cabextract'):
			raise SafeException(_("This package looks like a Microsoft Cabinet archive, but you don't have the 'cabextract' command "
					"I need to extract it. Install the package containing it first."))
	elif mime_type == 'application/x-apple-diskimage':
		if not find_in_path('hdiutil'):
			raise SafeException(_("This package looks like a Apple Disk Image, but you don't have the 'hdiutil' command "
					"I need to extract it."))
	elif mime_type == 'application/x-lzma-compressed-tar':
		pass	# We can get it through Zero Install
	elif mime_type == 'application/x-xz-compressed-tar':
		if not find_in_path('unxz'):
			raise SafeException(_("This package looks like a xz-compressed package, but you don't have the 'unxz' command "
					"I need to extract it. Install the package containing it (it's probably called 'xz-utils') "
					"first."))
	elif mime_type in ('application/x-compressed-tar', 'application/x-tar', 'application/x-ruby-gem'):
		pass
	else:
		from zeroinstall import version
		raise SafeException(_("Unsupported archive type '%(type)s' (for injector version %(version)s)") % {'type': mime_type, 'version': version})

def _exec_maybe_sandboxed(writable, prog, *args):
	"""execlp prog, with (only) the 'writable' directory writable if sandboxing is available.
	If no sandbox is available, run without a sandbox."""
	prog_path = find_in_path(prog)
	if not prog_path: raise Exception(_("'%s' not found in $PATH") % prog)
	if _pola_run is None:
		os.execlp(prog_path, prog_path, *args)
	# We have pola-shell :-)
	pola_args = ['--prog', prog_path, '-f', '/']
	for a in args:
		pola_args += ['-a', a]
	if writable:
		pola_args += ['-fw', writable]
	os.execl(_pola_run, _pola_run, *pola_args)

def unpack_archive(url, data, destdir, extract = None, type = None, start_offset = 0):
	"""Unpack stream 'data' into directory 'destdir'. If extract is given, extract just
	that sub-directory from the archive (i.e. destdir/extract will exist afterwards).
	Works out the format from the name.
	@type url: str
	@type data: file
	@type destdir: str
	@type extract: str | None
	@type type: str | None
	@type start_offset: int"""
	if type is None: type = type_from_url(url)
	if type is None: raise SafeException(_("Unknown extension (and no MIME type given) in '%s'") % url)
	if type == 'application/x-bzip-compressed-tar':
		extract_tar(data, destdir, extract, 'bzip2', start_offset)
	elif type == 'application/x-deb':
		extract_deb(data, destdir, extract, start_offset)
	elif type == 'application/x-rpm':
		extract_rpm(data, destdir, extract, start_offset)
	elif type == 'application/zip':
		extract_zip(data, destdir, extract, start_offset)
	elif type == 'application/x-tar':
		extract_tar(data, destdir, extract, None, start_offset)
	elif type == 'application/x-lzma-compressed-tar':
		extract_tar(data, destdir, extract, 'lzma', start_offset)
	elif type == 'application/x-xz-compressed-tar':
		extract_tar(data, destdir, extract, 'xz', start_offset)
	elif type == 'application/x-compressed-tar':
		extract_tar(data, destdir, extract, 'gzip', start_offset)
	elif type == 'application/vnd.ms-cab-compressed':
		extract_cab(data, destdir, extract, start_offset)
	elif type == 'application/x-apple-diskimage':
		extract_dmg(data, destdir, extract, start_offset)
	elif type == 'application/x-ruby-gem':
		extract_gem(data, destdir, extract, start_offset)
	else:
		raise SafeException(_('Unknown MIME type "%(type)s" for "%(url)s"') % {'type': type, 'url': url})

def extract_deb(stream, destdir, extract = None, start_offset = 0):
	"""@type stream: file
	@type destdir: str
	@type start_offset: int"""
	if extract:
		raise SafeException(_('Sorry, but the "extract" attribute is not yet supported for Debs'))

	stream.seek(start_offset)
	# ar can't read from stdin, so make a copy...
	deb_copy_name = os.path.join(destdir, 'archive.deb')
	with open(deb_copy_name, 'wb') as deb_copy:
		shutil.copyfileobj(stream, deb_copy)

	data_tar = None
	p = subprocess.Popen(('ar', 't', 'archive.deb'), stdout=subprocess.PIPE, cwd=destdir, universal_newlines=True)
	o = p.communicate()[0]
	for line in o.split('\n'):
		if line == 'data.tar':
			data_compression = None
		elif line == 'data.tar.gz':
			data_compression = 'gzip'
		elif line == 'data.tar.bz2':
			data_compression = 'bzip2'
		elif line == 'data.tar.lzma':
			data_compression = 'lzma'
		elif line == 'data.tar.xz':
			data_compression = 'xz'
		else:
			continue
		data_tar = line
		break
	else:
		raise SafeException(_("File is not a Debian package."))

	_extract(stream, destdir, ('ar', 'x', 'archive.deb', data_tar))
	os.unlink(deb_copy_name)
	data_name = os.path.join(destdir, data_tar)
	with open(data_name, 'rb') as data_stream:
		os.unlink(data_name)
		extract_tar(data_stream, destdir, None, data_compression)

def extract_rpm(stream, destdir, extract = None, start_offset = 0):
	if extract:
		raise SafeException(_('Sorry, but the "extract" attribute is not yet supported for RPMs'))
	fd, cpiopath = mkstemp('-rpm-tmp')
	try:
		child = os.fork()
		if child == 0:
			try:
				try:
					os.dup2(stream.fileno(), 0)
					os.lseek(0, start_offset, 0)
					os.dup2(fd, 1)
					_exec_maybe_sandboxed(None, 'rpm2cpio', '-')
				except:
					traceback.print_exc()
			finally:
				os._exit(1)
		id, status = os.waitpid(child, 0)
		assert id == child
		if status != 0:
			raise SafeException(_("rpm2cpio failed; can't unpack RPM archive; exit code %d") % status)
		os.close(fd)
		fd = None

		args = ['cpio', '-mid']
		if _gnu_cpio():
			args.append('--quiet')

		with open(cpiopath, 'rb') as cpio_stream:
			_extract(cpio_stream, destdir, args)
		# Set the mtime of every directory under 'tmp' to 0, since cpio doesn't
		# preserve directory mtimes.
		for root, dirs, files in os.walk(destdir):
			os.utime(root, (0, 0))
	finally:
		if fd is not None:
			os.close(fd)
		os.unlink(cpiopath)

def extract_gem(stream, destdir, extract = None, start_offset = 0):
	"""@type stream: file
	@type destdir: str
	@type start_offset: int
	@since: 0.53"""
	stream.seek(start_offset)
	payload = 'data.tar.gz'
	payload_stream = None
	tmpdir = mkdtemp(dir = destdir)
	try:
		extract_tar(stream, destdir=tmpdir, extract=payload, decompress=None)
		with open(os.path.join(tmpdir, payload), 'rb') as payload_stream:
			extract_tar(payload_stream, destdir=destdir, extract=extract, decompress='gzip')
	finally:
		if payload_stream:
			payload_stream.close()
		ro_rmtree(tmpdir)

def extract_cab(stream, destdir, extract, start_offset = 0):
	"""@since: 0.24"""
	if extract:
		raise SafeException(_('Sorry, but the "extract" attribute is not yet supported for Cabinet files'))

	stream.seek(start_offset)
	# cabextract can't read from stdin, so make a copy...
	cab_copy_name = os.path.join(destdir, 'archive.cab')
	cab_copy = open(cab_copy_name, 'wb')
	shutil.copyfileobj(stream, cab_copy)
	cab_copy.close()

	_extract(stream, destdir, ['cabextract', '-s', '-q', 'archive.cab'])
	os.unlink(cab_copy_name)

def extract_dmg(stream, destdir, extract, start_offset = 0):
	"""@since: 0.46"""
	if extract:
		raise SafeException(_('Sorry, but the "extract" attribute is not yet supported for DMGs'))

	stream.seek(start_offset)
	# hdiutil can't read from stdin, so make a copy...
	dmg_copy_name = os.path.join(destdir, 'archive.dmg')
	dmg_copy = open(dmg_copy_name, 'wb')
	shutil.copyfileobj(stream, dmg_copy)
	dmg_copy.close()

	mountpoint = mkdtemp(prefix='archive')
	subprocess.check_call(["hdiutil", "attach", "-quiet", "-mountpoint", mountpoint, "-nobrowse", dmg_copy_name])
	subprocess.check_call(["cp", "-pR"] + glob.glob("%s/*" % mountpoint) + [destdir])
	subprocess.check_call(["hdiutil", "detach", "-quiet", mountpoint])
	os.rmdir(mountpoint)
	os.unlink(dmg_copy_name)

def extract_zip(stream, destdir, extract, start_offset = 0):
	"""@type stream: file
	@type destdir: str
	@type extract: str
	@type start_offset: int"""
	if extract:
		# Limit the characters we accept, to avoid sending dodgy
		# strings to zip
		if not re.match('^[a-zA-Z0-9][- _a-zA-Z0-9.]*$', extract):
			raise SafeException(_('Illegal character in extract attribute'))

	stream.seek(start_offset)
	# unzip can't read from stdin, so make a copy...
	zip_copy_name = os.path.join(destdir, 'archive.zip')
	with open(zip_copy_name, 'wb') as zip_copy:
		shutil.copyfileobj(stream, zip_copy)

	args = ['unzip', '-q', '-o', 'archive.zip']

	if extract:
		args.append(extract + '/*')

	_extract(stream, destdir, args)
	os.unlink(zip_copy_name)

def extract_tar(stream, destdir, extract, decompress, start_offset = 0):
	"""@type stream: file
	@type destdir: str
	@type extract: str
	@type decompress: str
	@type start_offset: int"""
	if extract:
		# Limit the characters we accept, to avoid sending dodgy
		# strings to tar
		if not re.match('^[a-zA-Z0-9][- _a-zA-Z0-9.]*$', extract):
			raise SafeException(_('Illegal character in extract attribute'))

	assert decompress in [None, 'bzip2', 'gzip', 'lzma', 'xz']

	if _gnu_tar():
		ext_cmd = ['tar']
		if decompress:
			if decompress == 'bzip2':
				ext_cmd.append('--bzip2')
			elif decompress == 'gzip':
				ext_cmd.append('-z')
			elif decompress == 'lzma':
				unlzma = find_in_path('unlzma')
				if not unlzma:
					unlzma = os.path.abspath(os.path.join(os.path.dirname(__file__), '_unlzma'))
				ext_cmd.append('--use-compress-program=' + unlzma)
			elif decompress == 'xz':
				unxz = find_in_path('unxz')
				if not unxz:
					unxz = os.path.abspath(os.path.join(os.path.dirname(__file__), '_unxz'))
				ext_cmd.append('--use-compress-program=' + unxz)

		if recent_gnu_tar():
			ext_cmd.extend(('-x', '--no-same-owner', '--no-same-permissions'))
		else:
			ext_cmd.extend(('xf', '-'))

		if extract:
			ext_cmd.append(extract)

		_extract(stream, destdir, ext_cmd, start_offset)
	else:
		import tempfile

		# Since we don't have GNU tar, use python's tarfile module. This will probably
		# be a lot slower and we do not support lzma and xz; however, it is portable.
		# (lzma and xz are handled by first uncompressing stream to a temporary file.
		# this is simple to do, but less efficient than piping through the program)
		if decompress is None:
			rmode = 'r|'
		elif decompress == 'bzip2':
			rmode = 'r|bz2'
		elif decompress == 'gzip':
			rmode = 'r|gz'
		elif decompress == 'lzma':
			unlzma = find_in_path('unlzma')
			if not unlzma:
				unlzma = os.path.abspath(os.path.join(os.path.dirname(__file__), '_unlzma'))
			temp = tempfile.NamedTemporaryFile(suffix='.tar', mode='w+b')
			subprocess.check_call([unlzma], stdin=stream, stdout=temp)
			rmode = 'r|'
			stream = temp
		elif decompress == 'xz':
			unxz = find_in_path('unxz')
			if not unxz:
				unxz = os.path.abspath(os.path.join(os.path.dirname(__file__), '_unxz'))
			temp = tempfile.NamedTemporaryFile(suffix='.tar', mode='w+b')
			subprocess.check_call([unxz], stdin=stream, stdout=temp)
			rmode = 'r|'
			stream = temp
		else:
			raise SafeException(_('GNU tar unavailable; unsupported compression format: %s') % decompress)

		import tarfile

		stream.seek(start_offset)
		# Python 2.5.1 crashes if name is None; see Python bug #1706850
		tar = tarfile.open(name = '', mode = rmode, fileobj = stream)

		current_umask = os.umask(0)
		os.umask(current_umask)

		uid = gid = None
		try:
			uid = os.geteuid()
			gid = os.getegid()
		except:
			logger.debug(_("Can't get uid/gid"))

		def chmod_extract(tarinfo):
			# If any X bit is set, they all must be
			if tarinfo.mode & 0o111:
				tarinfo.mode |= 0o111

			# Everyone gets read and write (subject to the umask)
			# No special bits are allowed.
			tarinfo.mode = ((tarinfo.mode | 0o666) & ~current_umask) & 0o777

			# Don't change owner, even if run as root
			if uid:
				tarinfo.uid = uid
			if gid:
				tarinfo.gid = gid
			tar.extract(tarinfo, destdir)

		extracted_anything = False
		ext_dirs = []

		for tarinfo in tar:
			name = _u(tarinfo.name)
			if extract is None or \
			   name.startswith(extract + '/') or \
			   name == extract:
				if tarinfo.isdir():
					ext_dirs.append(tarinfo)

				chmod_extract(tarinfo)
				extracted_anything = True

		# Due to a bug in tarfile (python versions < 2.5), we have to manually
		# set the mtime of each directory that we extract after extracting everything.

		for tarinfo in ext_dirs:
			dirname = os.path.join(destdir, tarinfo.name)
			os.utime(dirname, (tarinfo.mtime, tarinfo.mtime))

		tar.close()

		if extract and not extracted_anything:
			raise SafeException(_('Unable to find specified file = %s in archive') % extract)
	
def _extract(stream, destdir, command, start_offset = 0):
	"""Run execvp('command') inside destdir in a child process, with
	stream seeked to 'start_offset' as stdin.
	@type stream: file
	@type destdir: str
	@type command: [str]
	@type start_offset: int"""

	# Some zip archives are missing timezone information; force consistent results
	child_env = os.environ.copy()
	child_env['TZ'] = 'GMT'

	stream.seek(start_offset)

	# TODO: use pola-run if available, once it supports fchmod
	child = subprocess.Popen(command, cwd = destdir, stdin = stream, stderr = subprocess.PIPE, env = child_env)

	unused, cerr = child.communicate()

	status = child.wait()
	if status != 0:
		raise SafeException(_('Failed to extract archive (using %(command)s); exit code %(status)d:\n%(err)s') % {'command': command, 'status': status, 'err': cerr.strip()})
