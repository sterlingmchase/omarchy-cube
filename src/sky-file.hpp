#pragma once
#include <cerrno>
#include <fcntl.h>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

inline std::vector<unsigned char> readBoundedFile(const std::string &path, size_t min, size_t max, bool settings = false) {
    // A path can become a FIFO before open; validate and read the same nonblocking descriptor.
    const int fd = open(path.c_str(), O_RDONLY | O_NONBLOCK | O_CLOEXEC | (settings ? O_NOFOLLOW : 0));
    if (fd < 0 && settings && errno == ENOENT)
        return {};
    if (fd < 0)
        throw std::runtime_error("Cannot open skydome");
    struct Close {
        int fd;
        ~Close() { close(fd); }
    } closeFile{fd};
    struct stat info {};
    if (fstat(fd, &info) < 0 || !S_ISREG(info.st_mode))
        throw std::runtime_error("Skydome must be a regular PNG or JPEG file");
    if (info.st_size < 0 || static_cast<size_t>(info.st_size) < min || static_cast<size_t>(info.st_size) > max)
        throw std::runtime_error("Skydome must be a readable PNG or JPEG smaller than 32 MiB");
    std::vector<unsigned char> bytes(static_cast<size_t>(info.st_size));
    size_t offset = 0;
    while (offset < bytes.size()) {
        const auto count = read(fd, bytes.data() + offset, bytes.size() - offset);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0)
            throw std::runtime_error("Cannot read skydome");
        offset += static_cast<size_t>(count);
    }
    return bytes;
}

inline std::vector<unsigned char> readSkyFile(const std::string &path) {
    return readBoundedFile(path, 24, 32 * 1024 * 1024);
}
