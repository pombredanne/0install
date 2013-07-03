BUILDDIR=_build
OCAMLBUILD=ocamlbuild -use-ocamlfind -build-dir "${BUILDDIR}"
ifeq ($(OS), Windows_NT)
  OCAMLBUILDFLAGS = -lflag -cclib -lflag -lshell32
endif

.PHONY: all ocaml byte doc clean tags test

all: test

test: ocaml
	$(OCAMLBUILD) $(OCAMLBUILDFLAGS) tests/test.native
	(cd tests && ../_build/tests/test.native)

ocaml: 
	$(OCAMLBUILD) $(OCAMLBUILDFLAGS) main.native
	if [ "$(OS)" = "Windows_NT" ];then make ocaml_windows; else make ocaml_posix; fi

ocaml_windows:
	cp _build/main.native _build/0install.exe
	cp 0install.exe.manifest _build/
	$(OCAMLBUILD) $(OCAMLBUILDFLAGS) runenv.native
	cp _build/runenv.native _build/0install-runenv.exe

ocaml_posix:
	cp _build/main.native _build/0install
	[ -f 0install ] || ln -s _build/0install 0install

byte:
	$(OCAMLBUILD) main.byte

doc:
	ocp-pack -o support.ml.tmp support/logging.ml support/common.ml support/utils.ml support/basedir.ml support/qdom.ml support/system.ml
	echo '(** General support code; not 0install-specific *)' > support.ml
	cat support.ml.tmp >> support.ml
	rm support.ml.tmp
	$(OCAMLBUILD) 0install.docdir/index.html
	rm support.ml

clean:
	$(OCAMLBUILD) -clean

tags:
	ctags *.ml support/*.ml