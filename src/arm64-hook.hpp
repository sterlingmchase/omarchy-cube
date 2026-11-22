#pragma once
// Minimal AArch64 inline function hook. Hyprland's CFunctionHook only knows how to
// relocate x86-64 prologues, so on arm64 hook() always fails. This replaces it with
// a 16-byte absolute branch (LDR X16, #8; BR X16; .quad dest) and a trampoline that
// holds the relocated original instructions followed by a branch back.
#include <cstdint>
#include <cstring>
#include <sys/mman.h>
#include <unistd.h>
#include <vector>

namespace cube_arm64 {

class Hook {
  public:
    Hook(void *target, void *destination) : m_target(target), m_destination(destination) {}
    ~Hook() { unhook(); }
    Hook(const Hook &) = delete;
    Hook &operator=(const Hook &) = delete;

    void *m_original = nullptr;

    bool hook() {
        if (m_active)
            return false;
        auto *src = static_cast<uint32_t *>(m_target);
        std::vector<uint32_t> code;
        for (int i = 0; i < PATCH_WORDS; ++i) {
            if (!relocate(src[i], reinterpret_cast<uint64_t>(src + i), code))
                return false;
        }
        emitAbsoluteJump(code, reinterpret_cast<uint64_t>(src + PATCH_WORDS));

        const size_t page = static_cast<size_t>(sysconf(_SC_PAGESIZE));
        const size_t bytes = code.size() * sizeof(uint32_t);
        const size_t size = (bytes + page - 1) / page * page;
        void *mem = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (mem == MAP_FAILED)
            return false;
        std::memcpy(mem, code.data(), bytes);
        if (mprotect(mem, size, PROT_READ | PROT_EXEC) != 0) {
            munmap(mem, size);
            return false;
        }
        __builtin___clear_cache(static_cast<char *>(mem), static_cast<char *>(mem) + bytes);
        m_trampoline = mem;
        m_trampolineSize = size;
        m_original = mem;

        std::memcpy(m_saved, src, sizeof(m_saved));
        uint32_t patch[PATCH_WORDS];
        patch[0] = 0x58000050; // LDR X16, #8
        patch[1] = 0xD61F0200; // BR X16
        const uint64_t dest = reinterpret_cast<uint64_t>(m_destination);
        std::memcpy(&patch[2], &dest, sizeof(dest));
        if (!writeCode(src, patch, sizeof(patch))) {
            munmap(m_trampoline, m_trampolineSize);
            m_trampoline = nullptr;
            m_original = nullptr;
            return false;
        }
        m_active = true;
        return true;
    }

    bool unhook() {
        if (!m_active)
            return false;
        if (!writeCode(m_target, m_saved, sizeof(m_saved)))
            return false;
        m_active = false;
        munmap(m_trampoline, m_trampolineSize);
        m_trampoline = nullptr;
        m_original = nullptr;
        return true;
    }

  private:
    static constexpr int PATCH_WORDS = 4;
    void *m_target;
    void *m_destination;
    void *m_trampoline = nullptr;
    size_t m_trampolineSize = 0;
    uint32_t m_saved[PATCH_WORDS] = {};
    bool m_active = false;

    static int64_t signExtend(uint64_t value, int bits) {
        const uint64_t m = 1ULL << (bits - 1);
        return static_cast<int64_t>((value ^ m) - m);
    }

    static void emitMov64(std::vector<uint32_t> &code, uint32_t rd, uint64_t value) {
        code.push_back(0xD2800000 | (static_cast<uint32_t>(value & 0xFFFF) << 5) | rd); // MOVZ
        for (uint32_t hw = 1; hw < 4; ++hw)
            code.push_back(0xF2800000 | (hw << 21) | (static_cast<uint32_t>((value >> (16 * hw)) & 0xFFFF) << 5) | rd); // MOVK
    }

    static void emitAbsoluteJump(std::vector<uint32_t> &code, uint64_t target) {
        code.push_back(0x58000050); // LDR X16, #8
        code.push_back(0xD61F0200); // BR X16
        code.push_back(static_cast<uint32_t>(target));
        code.push_back(static_cast<uint32_t>(target >> 32));
    }

    // Conditional branch: keep the condition, retarget it over a skip to an absolute jump.
    static void emitConditional(std::vector<uint32_t> &code, uint32_t insn, uint32_t immMask, int immShift, uint64_t target) {
        code.push_back((insn & ~immMask) | (2u << immShift)); // taken -> +8
        code.push_back(0x14000005);                           // B +20 (skip jump)
        emitAbsoluteJump(code, target);
    }

    static bool relocate(uint32_t insn, uint64_t pc, std::vector<uint32_t> &code) {
        const uint32_t rd = insn & 0x1F;
        if ((insn & 0x9F000000) == 0x90000000) { // ADRP
            const uint64_t imm = ((insn >> 5) & 0x7FFFF) << 2 | ((insn >> 29) & 3);
            emitMov64(code, rd, (pc & ~0xFFFULL) + (signExtend(imm, 21) << 12));
            return true;
        }
        if ((insn & 0x9F000000) == 0x10000000) { // ADR
            const uint64_t imm = ((insn >> 5) & 0x7FFFF) << 2 | ((insn >> 29) & 3);
            emitMov64(code, rd, pc + signExtend(imm, 21));
            return true;
        }
        if ((insn & 0x7C000000) == 0x14000000) { // B / BL
            const uint64_t target = pc + (signExtend(insn & 0x3FFFFFF, 26) << 2);
            if (insn & 0x80000000) { // BL
                code.push_back(0x58000050); // LDR X16, #8
                code.push_back(0x14000003); // B +12
                code.push_back(static_cast<uint32_t>(target));
                code.push_back(static_cast<uint32_t>(target >> 32));
                code.push_back(0xD63F0200); // BLR X16
            } else {
                emitAbsoluteJump(code, target);
            }
            return true;
        }
        if ((insn & 0xFF000010) == 0x54000000) { // B.cond
            emitConditional(code, insn, 0x7FFFF << 5, 5, pc + (signExtend((insn >> 5) & 0x7FFFF, 19) << 2));
            return true;
        }
        if ((insn & 0x7E000000) == 0x34000000) { // CBZ / CBNZ
            emitConditional(code, insn, 0x7FFFF << 5, 5, pc + (signExtend((insn >> 5) & 0x7FFFF, 19) << 2));
            return true;
        }
        if ((insn & 0x7E000000) == 0x36000000) { // TBZ / TBNZ
            emitConditional(code, insn, 0x3FFF << 5, 5, pc + (signExtend((insn >> 5) & 0x3FFF, 14) << 2));
            return true;
        }
        if ((insn & 0x3B000000) == 0x18000000) // LDR (literal) / PRFM (literal): not needed, refuse
            return false;
        // The relocation sequences clobber X16; refuse if the prologue itself writes X16/X17.
        if (rd == 16 || rd == 17)
            return false;
        code.push_back(insn);
        return true;
    }

    static bool writeCode(void *where, const void *data, size_t len) {
        const uintptr_t page = static_cast<uintptr_t>(sysconf(_SC_PAGESIZE));
        const uintptr_t start = reinterpret_cast<uintptr_t>(where) & ~(page - 1);
        const uintptr_t end = (reinterpret_cast<uintptr_t>(where) + len + page - 1) & ~(page - 1);
        if (mprotect(reinterpret_cast<void *>(start), end - start, PROT_READ | PROT_WRITE | PROT_EXEC) != 0)
            return false;
        std::memcpy(where, data, len);
        mprotect(reinterpret_cast<void *>(start), end - start, PROT_READ | PROT_EXEC);
        __builtin___clear_cache(static_cast<char *>(where), static_cast<char *>(where) + len);
        return true;
    }
};

} // namespace cube_arm64
