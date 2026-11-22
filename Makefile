CXX ?= c++
CPPFLAGS += $(shell pkg-config --cflags hyprland pixman-1 libdrm libturbojpeg pangocairo)
CXXFLAGS ?= -O2
CXXFLAGS += -std=c++23 -fPIC -fno-gnu-unique -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers
LDLIBS += $(shell pkg-config --libs pixman-1 libdrm cairo libturbojpeg pangocairo) -lGLESv2
.PHONY: all test clean
all: build/omarchy-cube.so
build:
	mkdir -p $@
build/omarchy-cube.so: src/plugin.cpp src/arm64-hook.hpp src/cube.hpp src/sky.hpp src/sky-file.hpp src/label.hpp | build
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -shared $< $(LDLIBS) -o $@.new
	mv $@.new $@
build/test: tests/cube.cpp src/cube.hpp | build
	$(CXX) -std=c++23 -Wall -Wextra -fsanitize=address,undefined -g $< -o $@
build/test-sky-file: tests/sky-file.cpp src/sky-file.hpp | build
	$(CXX) -std=c++23 -Wall -Wextra -Werror -fsanitize=address,undefined -g $< -Wl,--wrap=open -Wl,--wrap=fstat -o $@
test: build/test build/test-sky-file
	./build/test
	./build/test-sky-file
clean:
	rm -rf build
PREFIX ?= $(HOME)/.local
.PHONY: install uninstall
install: all
	install -d $(DESTDIR)$(PREFIX)/lib/hypr
	install -m755 build/omarchy-cube.so $(DESTDIR)$(PREFIX)/lib/hypr/omarchy-cube.so.new
	mv $(DESTDIR)$(PREFIX)/lib/hypr/omarchy-cube.so.new $(DESTDIR)$(PREFIX)/lib/hypr/omarchy-cube.so
uninstall:
	rm -f $(DESTDIR)$(PREFIX)/lib/hypr/omarchy-cube.so
