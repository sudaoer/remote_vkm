#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

#include <array>
#include <chrono>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>

namespace {

constexpr uint32_t kMagic = 0x4D4B5652; // b"RVKM" on little-endian wire.
constexpr uint8_t kVersion = 1;
constexpr size_t kFrameSize = 32;

constexpr uint8_t kTypeHello = 0;
constexpr uint8_t kTypeKey = 1;
constexpr uint8_t kTypeRel = 2;
constexpr uint8_t kTypeButton = 3;
constexpr uint8_t kTypeWheel = 4;

constexpr uint8_t kActionNone = 0;
constexpr uint8_t kActionPress = 1;
constexpr uint8_t kActionRelease = 2;

volatile sig_atomic_t g_stop = 0;

struct Options {
    std::string listen = "0.0.0.0";
    uint16_t port = 5533;
    bool dry_run = false;
};

struct Frame {
    uint8_t type = 0;
    uint8_t action = 0;
    uint8_t flags = 0;
    uint32_t code = 0;
    int32_t value1 = 0;
    int32_t value2 = 0;
    uint64_t sequence = 0;
    uint32_t reserved = 0;
};

void on_signal(int) {
    g_stop = 1;
}

uint32_t read_u32(const uint8_t* data) {
    return static_cast<uint32_t>(data[0]) |
           (static_cast<uint32_t>(data[1]) << 8) |
           (static_cast<uint32_t>(data[2]) << 16) |
           (static_cast<uint32_t>(data[3]) << 24);
}

int32_t read_i32(const uint8_t* data) {
    return static_cast<int32_t>(read_u32(data));
}

uint64_t read_u64(const uint8_t* data) {
    uint64_t value = 0;
    for (int i = 7; i >= 0; --i) {
        value = (value << 8) | data[i];
    }
    return value;
}

bool parse_frame(const std::array<uint8_t, kFrameSize>& bytes, Frame& frame, std::string& error) {
    const uint32_t magic = read_u32(bytes.data());
    if (magic != kMagic) {
        char buffer[64];
        snprintf(buffer, sizeof(buffer), "bad magic: 0x%08x", magic);
        error = buffer;
        return false;
    }

    const uint8_t version = bytes[4];
    if (version != kVersion) {
        char buffer[64];
        snprintf(buffer, sizeof(buffer), "unsupported protocol version: %u", version);
        error = buffer;
        return false;
    }

    frame.type = bytes[5];
    frame.action = bytes[6];
    frame.flags = bytes[7];
    frame.code = read_u32(bytes.data() + 8);
    frame.value1 = read_i32(bytes.data() + 12);
    frame.value2 = read_i32(bytes.data() + 16);
    frame.sequence = read_u64(bytes.data() + 20);
    frame.reserved = read_u32(bytes.data() + 28);
    return true;
}

bool read_exact(int fd, uint8_t* data, size_t size) {
    size_t offset = 0;
    while (offset < size) {
        const ssize_t got = recv(fd, data + offset, size - offset, 0);
        if (got == 0) {
            return false;
        }
        if (got < 0) {
            if (errno == EINTR) {
                if (g_stop) {
                    return false;
                }
                continue;
            }
            perror("recv");
            return false;
        }
        offset += static_cast<size_t>(got);
    }
    return true;
}

void usage(const char* argv0) {
    printf("Usage: %s [--listen 0.0.0.0] [--port 5533] [--dry-run]\n", argv0);
}

Options parse_options(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--listen" && i + 1 < argc) {
            options.listen = argv[++i];
        } else if (arg == "--port" && i + 1 < argc) {
            const long port = strtol(argv[++i], nullptr, 10);
            if (port <= 0 || port > 65535) {
                throw std::runtime_error("port must be in range 1..65535");
            }
            options.port = static_cast<uint16_t>(port);
        } else if (arg == "--dry-run") {
            options.dry_run = true;
        } else if (arg == "--help" || arg == "-h") {
            usage(argv[0]);
            exit(0);
        } else {
            throw std::runtime_error("unknown or incomplete argument: " + arg);
        }
    }
    return options;
}

class UinputDevice {
public:
    explicit UinputDevice(bool dry_run) : dry_run_(dry_run) {
        if (dry_run_) {
            puts("dry-run mode: events will be printed but not injected");
            return;
        }

        fd_ = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
        if (fd_ < 0) {
            throw std::runtime_error("failed to open /dev/uinput; run with sudo or configure udev permissions");
        }

        ioctl_checked(UI_SET_EVBIT, EV_KEY);
        ioctl_checked(UI_SET_EVBIT, EV_REL);

        for (int code = 0; code <= KEY_MAX; ++code) {
            if (ioctl(fd_, UI_SET_KEYBIT, code) < 0) {
                throw std::runtime_error("failed to configure uinput key bits");
            }
        }

        ioctl_checked(UI_SET_RELBIT, REL_X);
        ioctl_checked(UI_SET_RELBIT, REL_Y);
        ioctl_checked(UI_SET_RELBIT, REL_WHEEL);
        ioctl_checked(UI_SET_RELBIT, REL_HWHEEL);

        uinput_user_dev device {};
        snprintf(device.name, UINPUT_MAX_NAME_SIZE, "remote-vkm");
        device.id.bustype = BUS_USB;
        device.id.vendor = 0x524b;
        device.id.product = 0x0001;
        device.id.version = 1;

        if (write(fd_, &device, sizeof(device)) != static_cast<ssize_t>(sizeof(device))) {
            throw std::runtime_error("failed to write uinput device descriptor");
        }
        ioctl_checked(UI_DEV_CREATE, 0);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        puts("created /dev/uinput virtual keyboard/mouse");
    }

    ~UinputDevice() {
        if (fd_ >= 0) {
            ioctl(fd_, UI_DEV_DESTROY);
            close(fd_);
        }
    }

    UinputDevice(const UinputDevice&) = delete;
    UinputDevice& operator=(const UinputDevice&) = delete;

    void dispatch(const Frame& frame) {
        switch (frame.type) {
            case kTypeKey:
                key(frame.code, frame.action);
                break;
            case kTypeButton:
                button(frame.code, frame.action);
                break;
            case kTypeRel:
                rel(frame.value1, frame.value2);
                break;
            case kTypeWheel:
                wheel(frame.value1, frame.value2);
                break;
            default:
                fprintf(stderr, "seq=%llu unknown event type: %u\n",
                        static_cast<unsigned long long>(frame.sequence), frame.type);
                break;
        }
    }

    void release_all() {
        if (pressed_codes_.empty()) {
            return;
        }

        for (const uint16_t code : pressed_codes_) {
            if (dry_run_) {
                printf("release code=%u value=0\n", code);
            } else {
                emit(EV_KEY, code, 0);
            }
        }
        pressed_codes_.clear();
        sync();
    }

private:
    bool dry_run_ = false;
    int fd_ = -1;
    std::set<uint16_t> pressed_codes_;

    void ioctl_checked(unsigned long request, int value) {
        if (ioctl(fd_, request, value) < 0) {
            throw std::runtime_error("uinput ioctl failed");
        }
    }

    void emit(uint16_t type, uint16_t code, int32_t value) {
        input_event event {};
        event.type = type;
        event.code = code;
        event.value = value;
        if (write(fd_, &event, sizeof(event)) != static_cast<ssize_t>(sizeof(event))) {
            throw std::runtime_error("failed to write input event");
        }
    }

    void sync() {
        if (!dry_run_) {
            emit(EV_SYN, SYN_REPORT, 0);
        }
    }

    static int action_value(uint8_t action) {
        if (action == kActionPress) {
            return 1;
        }
        if (action == kActionRelease) {
            return 0;
        }
        return -1;
    }

    void key(uint32_t code, uint8_t action) {
        key_like("key", code, action);
    }

    void button(uint32_t code, uint8_t action) {
        key_like("button", code, action);
    }

    void key_like(const char* label, uint32_t code, uint8_t action) {
        const int value = action_value(action);
        if (value < 0 || code > KEY_MAX) {
            fprintf(stderr, "invalid %s event: code=%u action=%u\n", label, code, action);
            return;
        }
        const uint16_t ev_code = static_cast<uint16_t>(code);
        if (action == kActionPress) {
            pressed_codes_.insert(ev_code);
        } else if (action == kActionRelease) {
            pressed_codes_.erase(ev_code);
        }
        if (dry_run_) {
            printf("%s code=%u value=%d\n", label, code, value);
            return;
        }
        emit(EV_KEY, ev_code, value);
        sync();
    }

    void rel(int32_t dx, int32_t dy) {
        if (dry_run_) {
            printf("rel dx=%d dy=%d\n", dx, dy);
            return;
        }
        if (dx != 0) {
            emit(EV_REL, REL_X, dx);
        }
        if (dy != 0) {
            emit(EV_REL, REL_Y, dy);
        }
        sync();
    }

    void wheel(int32_t vertical, int32_t horizontal) {
        if (dry_run_) {
            printf("wheel vertical=%d horizontal=%d\n", vertical, horizontal);
            return;
        }
        if (vertical != 0) {
            emit(EV_REL, REL_WHEEL, vertical);
        }
        if (horizontal != 0) {
            emit(EV_REL, REL_HWHEEL, horizontal);
        }
        sync();
    }
};

int create_listener(const Options& options) {
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        throw std::runtime_error("socket failed");
    }

    int enabled = 1;
    if (setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof(enabled)) < 0) {
        close(fd);
        throw std::runtime_error("setsockopt SO_REUSEADDR failed");
    }

    sockaddr_in address {};
    address.sin_family = AF_INET;
    address.sin_port = htons(options.port);
    if (inet_pton(AF_INET, options.listen.c_str(), &address.sin_addr) != 1) {
        close(fd);
        throw std::runtime_error("listen address must be an IPv4 address");
    }

    if (bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
        close(fd);
        throw std::runtime_error("bind failed");
    }
    if (listen(fd, 1) < 0) {
        close(fd);
        throw std::runtime_error("listen failed");
    }

    const int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
        close(fd);
        throw std::runtime_error("failed to set listener non-blocking");
    }
    return fd;
}

void handle_client(int client_fd, UinputDevice& device) {
    std::array<uint8_t, kFrameSize> bytes {};
    Frame frame;
    std::string error;

    if (!read_exact(client_fd, bytes.data(), bytes.size())) {
        device.release_all();
        return;
    }
    if (!parse_frame(bytes, frame, error)) {
        fprintf(stderr, "protocol error: %s\n", error.c_str());
        device.release_all();
        return;
    }
    if (frame.type != kTypeHello) {
        fprintf(stderr, "protocol error: expected hello frame, got type %u\n", frame.type);
        device.release_all();
        return;
    }
    puts("client connected");

    while (!g_stop) {
        if (!read_exact(client_fd, bytes.data(), bytes.size())) {
            break;
        }
        if (!parse_frame(bytes, frame, error)) {
            fprintf(stderr, "protocol error: %s\n", error.c_str());
            break;
        }
        if (frame.type == kTypeHello) {
            continue;
        }
        device.dispatch(frame);
    }
    device.release_all();
}

} // namespace

int main(int argc, char** argv) {
    setvbuf(stdout, nullptr, _IOLBF, 0);
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    try {
        const Options options = parse_options(argc, argv);
        UinputDevice device(options.dry_run);
        const int listener = create_listener(options);
        printf("listening on %s:%u\n", options.listen.c_str(), options.port);

        while (!g_stop) {
            sockaddr_in peer {};
            socklen_t peer_len = sizeof(peer);
            const int client = accept(listener, reinterpret_cast<sockaddr*>(&peer), &peer_len);
            if (client < 0) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(50));
                    continue;
                }
                if (errno == EINTR && g_stop) {
                    break;
                }
                perror("accept");
                continue;
            }

            char peer_addr[INET_ADDRSTRLEN] {};
            inet_ntop(AF_INET, &peer.sin_addr, peer_addr, sizeof(peer_addr));
            printf("accepted connection from %s:%u\n", peer_addr, ntohs(peer.sin_port));
            handle_client(client, device);
            close(client);
            puts("client disconnected");
        }
        device.release_all();
        close(listener);
    } catch (const std::exception& exc) {
        fprintf(stderr, "error: %s\n", exc.what());
        return 1;
    }
    return 0;
}
