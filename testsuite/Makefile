
.PHONY: all clean
all clean:
	@export PLATFORM=`gcc -dM -E -xc /dev/null | grep WIN32 > /dev/null; \
	   if [ $$? == '0' ]; then echo '-mno-cygwin'; fi`;		     \
	   make -C function_template_sub $@; make -f Makefile.test $@
