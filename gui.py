from gpg import BadSignature
from policy import Policy
import download
import gtk, os
import sys

# Singleton Policy
policy = None

class GUIPolicy(Policy):
	window = None
	n_downloads = 0
	pulse = None

	def __init__(self, interface, prog, prog_args):
		Policy.__init__(self, interface)
		global policy
		assert policy is None
		policy = self

		import mainwindow
		self.window = mainwindow.MainWindow(prog, prog_args)
		self.window.browser.set_root(policy.get_interface(policy.root))

	def monitor_download(self, dl):
		error_stream = dl.start()
		def error_ready(src, cond):
			print src, "ready"
			got = os.read(src.fileno(), 100)
			if not got:
				error_stream.close()
				self.n_downloads -= 1
				if self.n_downloads == 0:
					self.window.progress.hide()
					gtk.timeout_remove(self.pulse)
					self.pulse = None
				data = dl.error_stream_closed()
				try:
					self.check_signed_data(dl, data)
				except BadSignature, ex:
					print >>sys.stderr, ex
				return False
			print "Errors: '%s'" % got
			print "(from %s)" % dl.url
			return True
			
		gtk.input_add(error_stream, gtk.gdk.INPUT_READ, error_ready)

		self.n_downloads += 1
		if self.pulse is None:
			progress = self.window.progress
			self.pulse = gtk.timeout_add(50, lambda: progress.pulse() or True)
			progress.show()

	def main(self):
		self.window.show()
		gtk.main()
