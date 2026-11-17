#include "../src/sky-file.hpp"
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <fcntl.h>
#include <stdexcept>
#include <sys/stat.h>
#include <unistd.h>

namespace {
std::string replacement, target;
bool replaceOnOpen = false, replaceOnStat = false;

void replacePath() {
    assert(::rename(replacement.c_str(), target.c_str()) == 0);
}

void writeFile(const std::string &path, const std::vector<unsigned char> &bytes) {
    std::ofstream output(path, std::ios::binary);
    output.write(reinterpret_cast<const char *>(bytes.data()), bytes.size());
    output.close();
    assert(output);
}

void rejected(const std::string &path) {
    // A blocking FIFO open must fail the test instead of hanging the test suite.
    alarm(2);
    const auto started = std::chrono::steady_clock::now();
    bool failed = false;
    try {
        (void)readSkyFile(path);
    } catch (const std::runtime_error &) {
        failed = true;
    }
    alarm(0);
    assert(failed);
    assert(std::chrono::steady_clock::now() - started < std::chrono::seconds(1));
}
}

extern "C" int __real_open(const char *, int, ...);
extern "C" int __wrap_open(const char *path, int flags, ...) {
    if (replaceOnOpen && target == path) {
        replaceOnOpen = false;
        replacePath();
    }
    return __real_open(path, flags, 0600);
}

extern "C" int __real_fstat(int, struct stat *);
extern "C" int __wrap_fstat(int fd, struct stat *info) {
    const int result = __real_fstat(fd, info);
    if (result == 0 && replaceOnStat) {
        replaceOnStat = false;
        replacePath();
    }
    return result;
}

int main() {
    char directory[] = "/tmp/omarchy-cube-sky-XXXXXX";
    assert(mkdtemp(directory));
    struct Cleanup {
        const char *path;
        ~Cleanup() { std::filesystem::remove_all(path); }
    } cleanup{directory};
    const std::string base = std::string(directory) + "/";
    const std::vector<unsigned char> original = {
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
        12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 254, 255};
    target = base + "image";
    writeFile(target, original);
    assert(readSkyFile(target) == original);
    assert(symlink(target.c_str(), (base + "link").c_str()) == 0);
    assert(readSkyFile(base + "link") == original);
    rejected(base + "missing");
    rejected(directory);
    writeFile(base + "small", std::vector<unsigned char>(23));
    rejected(base + "small");
    writeFile(base + "large", original);
    assert(truncate((base + "large").c_str(), 32 * 1024 * 1024 + 1) == 0);
    rejected(base + "large");
    assert(mkfifo((base + "fifo").c_str(), 0600) == 0);
    rejected(base + "fifo");

    // Replace the path after descriptor validation: reads must keep the opened inode.
    replacement = base + "replacement";
    writeFile(replacement, std::vector<unsigned char>(24, 42));
    replaceOnStat = true;
    assert(readSkyFile(target) == original);
    assert(!replaceOnStat);
    writeFile(target, original);
    assert(mkfifo(replacement.c_str(), 0600) == 0);
    replaceOnStat = true;
    alarm(2);
    assert(readSkyFile(target) == original);
    alarm(0);
    assert(!replaceOnStat);

    // A regular path swapped to a FIFO immediately before open must not block.
    assert(unlink(target.c_str()) == 0);
    writeFile(target, original);
    assert(mkfifo(replacement.c_str(), 0600) == 0);
    replaceOnOpen = true;
    rejected(target);
    assert(!replaceOnOpen);
}
