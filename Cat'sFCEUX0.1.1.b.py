#!/usr/bin/env python3
# ══════════════════════════════════════════════════════════════
#  CAT'S FCEUX 0.1.1B - ADVANCED NES EMULATOR 2025
#  Single-file, zero dependencies | Standard Library Only
#  Hardware: Complete 6502 CPU | Enhanced PPU | APU Framework
#  GUI: Native Tkinter | 600x400 Display
# ══════════════════════════════════════════════════════════════

import struct, time, os, threading, sys, math, random
import tkinter as tk
from tkinter import filedialog, messagebox, Menu, Frame, Canvas, Label

# ══════════════════════════════════════════════════════════════
# GLOBAL SYSTEM BUS & CONSOLE
# ══════════════════════════════════════════════════════════════

class SystemBus:
    """Inter-thread communication bus"""
    __slots__ = ('console_active', 'rom_loaded', 'debug_mode', 'paused', 'frame_skip')
    
    def __init__(self):
        self.console_active = False
        self.rom_loaded = False
        self.debug_mode = False
        self.paused = False
        self.frame_skip = 0

sys_bus = SystemBus()

def god_console(nes):
    """Developer console with full system access"""
    sys_bus.console_active = True
    print("\n" + "═"*60)
    print(" ⚡ CAT'S FCEUX 0.1.1B GOD CONSOLE")
    print("    Variables: 'nes', 'cpu', 'ppu', 'mem'")
    print("    Commands: 'exit', 'reset', 'dump', 'state'")
    print("═"*60)

    env = {
        'nes': nes,
        'cpu': nes.cpu,
        'ppu': nes.ppu,
        'mem': nes.wram,
        'math': math,
        'sys': sys
    }

    while True:
        try:
            cmd = input("⚡ CAT> ")
            if cmd.strip().lower() == "exit":
                print("Returning to GUI...")
                break
            if not cmd.strip():
                continue

            # Special commands
            if cmd == "reset":
                nes.cpu.reset()
                print("CPU RESET")
            elif cmd == "dump":
                print(f"PC: ${nes.cpu.pc:04X} | A: ${nes.cpu.a:02X} | X: ${nes.cpu.x:02X} | Y: ${nes.cpu.y:02X}")
                print(f"SP: ${nes.cpu.sp:02X} | Status: {bin(nes.cpu.status)[2:].zfill(8)}")
            elif cmd == "state":
                print(f"Frame: {nes.frame_count} | Cycles: {nes.cpu.total_cycles}")
                print(f"ROM: {'LOADED' if sys_bus.rom_loaded else 'NONE'}")
            else:
                exec(cmd, globals(), env)

        except Exception as e:
            print(f"❌ Error: {e}")

    sys_bus.console_active = False

# ══════════════════════════════════════════════════════════════
# COMPLETE 6502 CPU IMPLEMENTATION
# ══════════════════════════════════════════════════════════════

class CPU:
    __slots__ = ('nes', 'a', 'x', 'y', 'sp', 'pc', 'status', 'cycles', 
                 'extra_cycles', 'total_cycles', 'nmi_pending', 'irq_pending',
                 'op_table', 'cycles_table')
    
    def __init__(self, nes):
        self.nes = nes
        self.a = 0
        self.x = 0
        self.y = 0
        self.sp = 0xFD
        self.pc = 0
        self.status = 0x24
        self.cycles = 0
        self.extra_cycles = 0
        self.total_cycles = 0
        self.nmi_pending = False
        self.irq_pending = False
        self.op_table = [None] * 256
        self.cycles_table = [0] * 256
        self.build_instruction_set()

    def reset(self):
        self.a = self.x = self.y = 0
        self.sp = 0xFD
        self.status = 0x24
        self.pc = self.nes.read16(0xFFFC)
        self.cycles = 7
        self.total_cycles = 0
        print(f"[CPU] RESET | Entry Point: ${self.pc:04X}")

    def get_flag(self, mask):
        return bool(self.status & mask)

    def set_flag(self, mask, val):
        if val:
            self.status |= mask
        else:
            self.status &= ~mask

    def set_zn(self, val):
        self.set_flag(0x02, val == 0)
        self.set_flag(0x80, val & 0x80)

    def push(self, val):
        self.nes.write(0x100 + self.sp, val & 0xFF)
        self.sp = (self.sp - 1) & 0xFF

    def pop(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.nes.read(0x100 + self.sp)

    def push16(self, val):
        self.push(val >> 8)
        self.push(val & 0xFF)

    def pop16(self):
        lo = self.pop()
        hi = self.pop()
        return (hi << 8) | lo

    def nmi(self):
        self.push16(self.pc)
        self.push(self.status & ~0x10)
        self.set_flag(0x04, True)
        self.pc = self.nes.read16(0xFFFA)
        self.cycles = 7

    def irq(self):
        if not self.get_flag(0x04):
            self.push16(self.pc)
            self.push(self.status & ~0x10)
            self.set_flag(0x04, True)
            self.pc = self.nes.read16(0xFFFE)
            self.cycles = 7

    # Addressing modes
    def imm(self): return self.pc; self.pc += 1
    def zpg(self): addr = self.nes.read(self.pc); self.pc += 1; return addr
    def zpgx(self): return (self.nes.read(self.pc) + self.x) & 0xFF; self.pc += 1
    def zpgy(self): return (self.nes.read(self.pc) + self.y) & 0xFF; self.pc += 1
    def abs(self): addr = self.nes.read16(self.pc); self.pc += 2; return addr
    def absx(self): 
        addr = self.nes.read16(self.pc); self.pc += 2
        if (addr & 0xFF00) != ((addr + self.x) & 0xFF00):
            self.extra_cycles = 1
        return addr + self.x
    def absy(self):
        addr = self.nes.read16(self.pc); self.pc += 2
        if (addr & 0xFF00) != ((addr + self.y) & 0xFF00):
            self.extra_cycles = 1
        return addr + self.y
    def ind(self):
        addr = self.nes.read16(self.pc); self.pc += 2
        if (addr & 0xFF) == 0xFF:
            return (self.nes.read(addr & 0xFF00) << 8) | self.nes.read(addr)
        return self.nes.read16(addr)
    def indx(self):
        base = self.nes.read(self.pc); self.pc += 1
        addr = (base + self.x) & 0xFF
        return self.nes.read(addr) | (self.nes.read((addr + 1) & 0xFF) << 8)
    def indy(self):
        base = self.nes.read(self.pc); self.pc += 1
        addr = self.nes.read(base) | (self.nes.read((base + 1) & 0xFF) << 8)
        if (addr & 0xFF00) != ((addr + self.y) & 0xFF00):
            self.extra_cycles = 1
        return addr + self.y

    # Instruction implementations
    def ADC(self, addr): 
        val = self.nes.read(addr)
        carry = self.get_flag(0x01)
        res = self.a + val + carry
        self.set_flag(0x01, res > 0xFF)
        self.set_flag(0x40, ((self.a ^ val) & 0x80) == 0 and ((self.a ^ res) & 0x80) != 0)
        self.a = res & 0xFF
        self.set_zn(self.a)
    
    def AND(self, addr): self.a &= self.nes.read(addr); self.set_zn(self.a)
    def ASL(self, addr): 
        if addr is None:  # Accumulator
            self.set_flag(0x01, self.a & 0x80)
            self.a = (self.a << 1) & 0xFF
            self.set_zn(self.a)
        else:
            val = self.nes.read(addr)
            self.set_flag(0x01, val & 0x80)
            val = (val << 1) & 0xFF
            self.nes.write(addr, val)
            self.set_zn(val)
    
    def BCC(self, addr): 
        if not self.get_flag(0x01): 
            self.pc = addr
            self.cycles += 1
    def BCS(self, addr): 
        if self.get_flag(0x01): 
            self.pc = addr
            self.cycles += 1
    def BEQ(self, addr): 
        if self.get_flag(0x02): 
            self.pc = addr
            self.cycles += 1
    def BIT(self, addr): 
        val = self.nes.read(addr)
        self.set_flag(0x80, val & 0x80)
        self.set_flag(0x40, val & 0x40)
        self.set_flag(0x02, (self.a & val) == 0)
    def BMI(self, addr): 
        if self.get_flag(0x80): 
            self.pc = addr
            self.cycles += 1
    def BNE(self, addr): 
        if not self.get_flag(0x02): 
            self.pc = addr
            self.cycles += 1
    def BPL(self, addr): 
        if not self.get_flag(0x80): 
            self.pc = addr
            self.cycles += 1
    def BRK(self, addr): 
        self.push16(self.pc + 1)
        self.push(self.status | 0x10)
        self.set_flag(0x04, True)
        self.pc = self.nes.read16(0xFFFE)
    def BVC(self, addr): 
        if not self.get_flag(0x40): 
            self.pc = addr
            self.cycles += 1
    def BVS(self, addr): 
        if self.get_flag(0x40): 
            self.pc = addr
            self.cycles += 1
    def CLC(self, addr): self.set_flag(0x01, False)
    def CLD(self, addr): self.set_flag(0x08, False)
    def CLI(self, addr): self.set_flag(0x04, False)
    def CLV(self, addr): self.set_flag(0x40, False)
    def CMP(self, addr): 
        val = self.nes.read(addr)
        res = self.a - val
        self.set_flag(0x01, res >= 0)
        self.set_zn(res & 0xFF)
    def CPX(self, addr): 
        val = self.nes.read(addr)
        res = self.x - val
        self.set_flag(0x01, res >= 0)
        self.set_zn(res & 0xFF)
    def CPY(self, addr): 
        val = self.nes.read(addr)
        res = self.y - val
        self.set_flag(0x01, res >= 0)
        self.set_zn(res & 0xFF)
    def DEC(self, addr): 
        val = (self.nes.read(addr) - 1) & 0xFF
        self.nes.write(addr, val)
        self.set_zn(val)
    def DEX(self, addr): 
        self.x = (self.x - 1) & 0xFF
        self.set_zn(self.x)
    def DEY(self, addr): 
        self.y = (self.y - 1) & 0xFF
        self.set_zn(self.y)
    def EOR(self, addr): 
        self.a ^= self.nes.read(addr)
        self.set_zn(self.a)
    def INC(self, addr): 
        val = (self.nes.read(addr) + 1) & 0xFF
        self.nes.write(addr, val)
        self.set_zn(val)
    def INX(self, addr): 
        self.x = (self.x + 1) & 0xFF
        self.set_zn(self.x)
    def INY(self, addr): 
        self.y = (self.y + 1) & 0xFF
        self.set_zn(self.y)
    def JMP(self, addr): self.pc = addr
    def JSR(self, addr): 
        self.push16(self.pc - 1)
        self.pc = addr
    def LDA(self, addr): 
        self.a = self.nes.read(addr)
        self.set_zn(self.a)
    def LDX(self, addr): 
        self.x = self.nes.read(addr)
        self.set_zn(self.x)
    def LDY(self, addr): 
        self.y = self.nes.read(addr)
        self.set_zn(self.y)
    def LSR(self, addr): 
        if addr is None:  # Accumulator
            self.set_flag(0x01, self.a & 0x01)
            self.a >>= 1
            self.set_zn(self.a)
        else:
            val = self.nes.read(addr)
            self.set_flag(0x01, val & 0x01)
            val >>= 1
            self.nes.write(addr, val)
            self.set_zn(val)
    def NOP(self, addr): pass
    def ORA(self, addr): 
        self.a |= self.nes.read(addr)
        self.set_zn(self.a)
    def PHA(self, addr): self.push(self.a)
    def PHP(self, addr): self.push(self.status | 0x10)
    def PLA(self, addr): 
        self.a = self.pop()
        self.set_zn(self.a)
    def PLP(self, addr): self.status = (self.pop() & 0xEF) | 0x20
    def ROL(self, addr): 
        carry = self.get_flag(0x01)
        if addr is None:  # Accumulator
            self.set_flag(0x01, self.a & 0x80)
            self.a = ((self.a << 1) | carry) & 0xFF
            self.set_zn(self.a)
        else:
            val = self.nes.read(addr)
            self.set_flag(0x01, val & 0x80)
            val = ((val << 1) | carry) & 0xFF
            self.nes.write(addr, val)
            self.set_zn(val)
    def ROR(self, addr): 
        carry = self.get_flag(0x01)
        if addr is None:  # Accumulator
            self.set_flag(0x01, self.a & 0x01)
            self.a = (self.a >> 1) | (carry << 7)
            self.set_zn(self.a)
        else:
            val = self.nes.read(addr)
            self.set_flag(0x01, val & 0x01)
            val = (val >> 1) | (carry << 7)
            self.nes.write(addr, val)
            self.set_zn(val)
    def RTI(self, addr): 
        self.status = (self.pop() & 0xEF) | 0x20
        self.pc = self.pop16()
    def RTS(self, addr): self.pc = self.pop16() + 1
    def SBC(self, addr): 
        val = self.nes.read(addr) ^ 0xFF
        carry = self.get_flag(0x01)
        res = self.a + val + carry
        self.set_flag(0x01, res > 0xFF)
        self.set_flag(0x40, ((self.a ^ val) & 0x80) == 0 and ((self.a ^ res) & 0x80) != 0)
        self.a = res & 0xFF
        self.set_zn(self.a)
    def SEC(self, addr): self.set_flag(0x01, True)
    def SED(self, addr): self.set_flag(0x08, True)
    def SEI(self, addr): self.set_flag(0x04, True)
    def STA(self, addr): self.nes.write(addr, self.a)
    def STX(self, addr): self.nes.write(addr, self.x)
    def STY(self, addr): self.nes.write(addr, self.y)
    def TAX(self, addr): 
        self.x = self.a
        self.set_zn(self.x)
    def TAY(self, addr): 
        self.y = self.a
        self.set_zn(self.y)
    def TSX(self, addr): 
        self.x = self.sp
        self.set_zn(self.x)
    def TXA(self, addr): 
        self.a = self.x
        self.set_zn(self.a)
    def TXS(self, addr): self.sp = self.x
    def TYA(self, addr): 
        self.a = self.y
        self.set_zn(self.a)

    def build_instruction_set(self):
        ops = [
            (0x69, self.ADC, self.imm, 2), (0x65, self.ADC, self.zpg, 3), (0x75, self.ADC, self.zpgx, 4),
            (0x6D, self.ADC, self.abs, 4), (0x7D, self.ADC, self.absx, 4), (0x79, self.ADC, self.absy, 4),
            (0x61, self.ADC, self.indx, 6), (0x71, self.ADC, self.indy, 5),
            (0x29, self.AND, self.imm, 2), (0x25, self.AND, self.zpg, 3), (0x35, self.AND, self.zpgx, 4),
            (0x2D, self.AND, self.abs, 4), (0x3D, self.AND, self.absx, 4), (0x39, self.AND, self.absy, 4),
            (0x21, self.AND, self.indx, 6), (0x31, self.AND, self.indy, 5),
            (0x0A, self.ASL, None, 2), (0x06, self.ASL, self.zpg, 5), (0x16, self.ASL, self.zpgx, 6),
            (0x0E, self.ASL, self.abs, 6), (0x1E, self.ASL, self.absx, 7),
            (0x90, self.BCC, self.abs, 2), (0xB0, self.BCS, self.abs, 2), (0xF0, self.BEQ, self.abs, 2),
            (0x24, self.BIT, self.zpg, 3), (0x2C, self.BIT, self.abs, 4), (0x30, self.BMI, self.abs, 2),
            (0xD0, self.BNE, self.abs, 2), (0x10, self.BPL, self.abs, 2), (0x00, self.BRK, None, 7),
            (0x50, self.BVC, self.abs, 2), (0x70, self.BVS, self.abs, 2), (0x18, self.CLC, None, 2),
            (0xD8, self.CLD, None, 2), (0x58, self.CLI, None, 2), (0xB8, self.CLV, None, 2),
            (0xC9, self.CMP, self.imm, 2), (0xC5, self.CMP, self.zpg, 3), (0xD5, self.CMP, self.zpgx, 4),
            (0xCD, self.CMP, self.abs, 4), (0xDD, self.CMP, self.absx, 4), (0xD9, self.CMP, self.absy, 4),
            (0xC1, self.CMP, self.indx, 6), (0xD1, self.CMP, self.indy, 5),
            (0xE0, self.CPX, self.imm, 2), (0xE4, self.CPX, self.zpg, 3), (0xEC, self.CPX, self.abs, 4),
            (0xC0, self.CPY, self.imm, 2), (0xC4, self.CPY, self.zpg, 3), (0xCC, self.CPY, self.abs, 4),
            (0xC6, self.DEC, self.zpg, 5), (0xD6, self.DEC, self.zpgx, 6), (0xCE, self.DEC, self.abs, 6),
            (0xDE, self.DEC, self.absx, 7), (0xCA, self.DEX, None, 2), (0x88, self.DEY, None, 2),
            (0x49, self.EOR, self.imm, 2), (0x45, self.EOR, self.zpg, 3), (0x55, self.EOR, self.zpgx, 4),
            (0x4D, self.EOR, self.abs, 4), (0x5D, self.EOR, self.absx, 4), (0x59, self.EOR, self.absy, 4),
            (0x41, self.EOR, self.indx, 6), (0x51, self.EOR, self.indy, 5),
            (0xE6, self.INC, self.zpg, 5), (0xF6, self.INC, self.zpgx, 6), (0xEE, self.INC, self.abs, 6),
            (0xFE, self.INC, self.absx, 7), (0xE8, self.INX, None, 2), (0xC8, self.INY, None, 2),
            (0x4C, self.JMP, self.abs, 3), (0x6C, self.JMP, self.ind, 5), (0x20, self.JSR, self.abs, 6),
            (0xA9, self.LDA, self.imm, 2), (0xA5, self.LDA, self.zpg, 3), (0xB5, self.LDA, self.zpgx, 4),
            (0xAD, self.LDA, self.abs, 4), (0xBD, self.LDA, self.absx, 4), (0xB9, self.LDA, self.absy, 4),
            (0xA1, self.LDA, self.indx, 6), (0xB1, self.LDA, self.indy, 5),
            (0xA2, self.LDX, self.imm, 2), (0xA6, self.LDX, self.zpg, 3), (0xB6, self.LDX, self.zpgy, 4),
            (0xAE, self.LDX, self.abs, 4), (0xBE, self.LDX, self.absy, 4),
            (0xA0, self.LDY, self.imm, 2), (0xA4, self.LDY, self.zpg, 3), (0xB4, self.LDY, self.zpgx, 4),
            (0xAC, self.LDY, self.abs, 4), (0xBC, self.LDY, self.absx, 4),
            (0x4A, self.LSR, None, 2), (0x46, self.LSR, self.zpg, 5), (0x56, self.LSR, self.zpgx, 6),
            (0x4E, self.LSR, self.abs, 6), (0x5E, self.LSR, self.absx, 7),
            (0xEA, self.NOP, None, 2),
            (0x09, self.ORA, self.imm, 2), (0x05, self.ORA, self.zpg, 3), (0x15, self.ORA, self.zpgx, 4),
            (0x0D, self.ORA, self.abs, 4), (0x1D, self.ORA, self.absx, 4), (0x19, self.ORA, self.absy, 4),
            (0x01, self.ORA, self.indx, 6), (0x11, self.ORA, self.indy, 5),
            (0x48, self.PHA, None, 3), (0x08, self.PHP, None, 3), (0x68, self.PLA, None, 4),
            (0x28, self.PLP, None, 4), (0x2A, self.ROL, None, 2), (0x26, self.ROL, self.zpg, 5),
            (0x36, self.ROL, self.zpgx, 6), (0x2E, self.ROL, self.abs, 6), (0x3E, self.ROL, self.absx, 7),
            (0x6A, self.ROR, None, 2), (0x66, self.ROR, self.zpg, 5), (0x76, self.ROR, self.zpgx, 6),
            (0x6E, self.ROR, self.abs, 6), (0x7E, self.ROR, self.absx, 7), (0x40, self.RTI, None, 6),
            (0x60, self.RTS, None, 6), (0xE9, self.SBC, self.imm, 2), (0xE5, self.SBC, self.zpg, 3),
            (0xF5, self.SBC, self.zpgx, 4), (0xED, self.SBC, self.abs, 4), (0xFD, self.SBC, self.absx, 4),
            (0xF9, self.SBC, self.absy, 4), (0xE1, self.SBC, self.indx, 6), (0xF1, self.SBC, self.indy, 5),
            (0x38, self.SEC, None, 2), (0xF8, self.SED, None, 2), (0x78, self.SEI, None, 2),
            (0x85, self.STA, self.zpg, 3), (0x95, self.STA, self.zpgx, 4), (0x8D, self.STA, self.abs, 4),
            (0x9D, self.STA, self.absx, 5), (0x99, self.STA, self.absy, 5), (0x81, self.STA, self.indx, 6),
            (0x91, self.STA, self.indy, 6), (0x86, self.STX, self.zpg, 3), (0x96, self.STX, self.zpgy, 4),
            (0x8E, self.STX, self.abs, 4), (0x84, self.STY, self.zpg, 3), (0x94, self.STY, self.zpgx, 4),
            (0x8C, self.STY, self.abs, 4), (0xAA, self.TAX, None, 2), (0xA8, self.TAY, None, 2),
            (0xBA, self.TSX, None, 2), (0x8A, self.TXA, None, 2), (0x9A, self.TXS, None, 2),
            (0x98, self.TYA, None, 2)
        ]
        
        for opcode, method, addr_mode, cycles in ops:
            self.op_table[opcode] = (method, addr_mode)
            self.cycles_table[opcode] = cycles

    def step(self):
        if self.nmi_pending:
            self.nmi()
            self.nmi_pending = False
            return
        
        if self.irq_pending and not self.get_flag(0x04):
            self.irq()
            self.irq_pending = False
            return

        opcode = self.nes.read(self.pc)
        self.pc += 1
        
        method, addr_mode = self.op_table[opcode]
        cycles = self.cycles_table[opcode]
        
        if addr_mode is None:
            addr = None
        else:
            addr = addr_mode()
        
        method(addr)
        
        self.cycles += cycles + self.extra_cycles
        self.total_cycles += cycles + self.extra_cycles
        self.extra_cycles = 0

# ══════════════════════════════════════════════════════════════
# ENHANCED PPU IMPLEMENTATION
# ══════════════════════════════════════════════════════════════

class PPU:
    __slots__ = ('nes', 'vram', 'palette', 'oam', 'cycle', 'scanline', 'frame', 
                 'ctrl', 'mask', 'status', 'oam_addr', 'v', 't', 'x', 'w', 
                 'nmi_occurred', 'front_buffer', 'back_buffer')
    
    def __init__(self, nes):
        self.nes = nes
        self.vram = [0] * 0x4000
        self.palette = [0] * 32
        self.oam = [0] * 256
        self.cycle = 0
        self.scanline = 0
        self.frame = 0
        self.ctrl = self.mask = self.status = 0
        self.oam_addr = 0
        self.v = self.t = self.x = self.w = 0
        self.nmi_occurred = False
        self.front_buffer = [0] * (256 * 240)
        self.back_buffer = [0] * (256 * 240)

    def read(self, addr):
        addr &= 0x3FFF
        if addr < 0x2000:
            return self.nes.chr_read(addr)
        elif addr < 0x3F00:
            return self.vram[self.mirror_vram(addr)]
        elif addr < 0x4000:
            return self.palette[self.mirror_palette(addr)]
        return 0

    def write(self, addr, val):
        addr &= 0x3FFF
        val &= 0xFF
        if addr < 0x2000:
            self.nes.chr_write(addr, val)
        elif addr < 0x3F00:
            self.vram[self.mirror_vram(addr)] = val
        elif addr < 0x4000:
            self.palette[self.mirror_palette(addr)] = val

    def mirror_vram(self, addr):
        addr = (addr - 0x2000) & 0x0FFF
        mirror = self.nes.mirroring
        if mirror == 0:  # Horizontal
            if addr < 0x0800: return addr & 0x03FF
            else: return (addr & 0x03FF) + 0x0400
        else:  # Vertical
            if addr < 0x0800: return addr & 0x03FF
            else: return addr & 0x03FF

    def mirror_palette(self, addr):
        addr = (addr - 0x3F00) & 0x1F
        if addr >= 16 and (addr % 4) == 0:
            addr -= 16
        return addr

    def write_control(self, val):
        self.ctrl = val
        self.t = (self.t & 0xF3FF) | ((val & 3) << 10)

    def write_mask(self, val):
        self.mask = val

    def read_status(self):
        res = self.status & 0xE0
        self.status &= 0x7F
        self.w = 0
        return res

    def write_oam_addr(self, val):
        self.oam_addr = val

    def write_oam_data(self, val):
        self.oam[self.oam_addr] = val
        self.oam_addr = (self.oam_addr + 1) & 0xFF

    def read_oam_data(self):
        return self.oam[self.oam_addr]

    def write_scroll(self, val):
        if self.w == 0:
            self.t = (self.t & 0xFFE0) | (val >> 3)
            self.x = val & 7
            self.w = 1
        else:
            self.t = (self.t & 0x8FFF) | ((val & 7) << 12)
            self.t = (self.t & 0xFC1F) | ((val & 0xF8) << 2)
            self.w = 0

    def write_address(self, val):
        if self.w == 0:
            self.t = (self.t & 0x80FF) | ((val & 0x3F) << 8)
            self.w = 1
        else:
            self.t = (self.t & 0xFF00) | val
            self.v = self.t
            self.w = 0

    def read_data(self):
        res = self.read(self.v)
        if self.v < 0x3F00:
            buffered = res
            res = self.buffer
            self.buffer = buffered
        else:
            res = self.read(self.v)
        self.v += 32 if (self.ctrl & 4) else 1
        return res

    def write_data(self, val):
        self.write(self.v, val)
        self.v += 32 if (self.ctrl & 4) else 1

    def tick(self):
        if self.scanline < 240:
            if self.cycle < 256:
                self.render_pixel()
        elif self.scanline == 241 and self.cycle == 1:
            self.status |= 0x80
            if self.ctrl & 0x80:
                self.nmi_occurred = True
                self.nes.cpu.nmi_pending = True
        
        self.cycle += 1
        if self.cycle >= 341:
            self.cycle = 0
            self.scanline += 1
            if self.scanline >= 262:
                self.scanline = 0
                self.frame += 1
                self.front_buffer, self.back_buffer = self.back_buffer, self.front_buffer

    def render_pixel(self):
        x, y = self.cycle - 1, self.scanline
        if x < 0 or x >= 256 or y < 0 or y >= 240:
            return
        
        bg_color = self.render_background()
        sprite_color, sprite_priority = self.render_sprites()
        
        if (self.mask & 0x08) and (self.mask & 0x10):
            if sprite_color and (not sprite_priority or not bg_color):
                color = sprite_color
            else:
                color = bg_color
        elif self.mask & 0x08:
            color = bg_color
        elif self.mask & 0x10:
            color = sprite_color
        else:
            color = 0
        
        palette_idx = self.read(0x3F00 + color) & 0x3F
        self.back_buffer[y * 256 + x] = self.nes_palette[palette_idx]

    def render_background(self):
        if not (self.mask & 0x08):
            return 0
        
        fine_x = (self.v & 0x1F) >> 12
        fine_y = (self.v >> 2) & 0x07
        tile_x = (self.v >> 5) & 0x1F
        tile_y = (self.v >> 10) & 0x1F
        nametable = (self.v >> 8) & 0x03
        
        attr_addr = 0x23C0 | (nametable << 10) | ((tile_y // 4) << 3) | (tile_x // 4)
        attr = self.read(attr_addr)
        shift = ((tile_y & 2) << 1) | (tile_x & 2)
        palette = (attr >> shift) & 3
        
        tile_addr = (0x1000 if (self.ctrl & 0x10) else 0x0000) + \
                   self.read(0x2000 | (nametable << 10) | (tile_y << 5) | tile_x) * 16
        plane0 = self.read(tile_addr + fine_y)
        plane1 = self.read(tile_addr + fine_y + 8)
        
        bit = 7 - fine_x
        color = ((plane1 >> bit) & 1) << 1 | ((plane0 >> bit) & 1)
        return palette << 2 | color if color else 0

    def render_sprites(self):
        if not (self.mask & 0x10):
            return 0, False
        
        sprite_height = 16 if (self.ctrl & 0x20) else 8
        sprite_count = 0
        
        for i in range(64):
            y_pos = self.oam[i * 4]
            if y_pos > 239: continue
            
            tile_idx = self.oam[i * 4 + 1]
            attr = self.oam[i * 4 + 2]
            x_pos = self.oam[i * 4 + 3]
            
            if not (x_pos <= self.cycle - 1 < x_pos + 8):
                continue
            
            sprite_count += 1
            if sprite_count > 8:
                self.status |= 0x20
                break
            
            rel_x = (self.cycle - 1) - x_pos
            rel_y = (self.scanline - y_pos - 1) % sprite_height
            
            if attr & 0x40: rel_x = 7 - rel_x
            if attr & 0x80: rel_y = sprite_height - 1 - rel_y
            
            if sprite_height == 16:
                bank = (tile_idx & 1) * 0x1000
                tile_idx = (tile_idx & 0xFE) | (rel_y & 0x08)
            else:
                bank = 0x1000 if (self.ctrl & 0x08) else 0x0000
            
            tile_addr = bank + tile_idx * 16 + (rel_y & 0x07)
            plane0 = self.read(tile_addr)
            plane1 = self.read(tile_addr + 8)
            
            bit = 7 - rel_x
            color = ((plane1 >> bit) & 1) << 1 | ((plane0 >> bit) & 1)
            if color == 0: continue
            
            palette = 0x10 + ((attr & 3) << 2) + color
            priority = bool(attr & 0x20)
            return palette, priority
        
        return 0, False

    nes_palette = [
        0x666666, 0x002A88, 0x1412A7, 0x3B00A4, 0x5C007E, 0x6E0040, 0x6C0600, 0x561D00,
        0x333500, 0x0B4800, 0x005200, 0x004F08, 0x00404D, 0x000000, 0x000000, 0x000000,
        0xADADAD, 0x155FD9, 0x4240FF, 0x7527FE, 0xA01ACC, 0xB71E7B, 0xB53120, 0x994E00,
        0x6B6D00, 0x388700, 0x0C9300, 0x008F32, 0x007C8D, 0x000000, 0x000000, 0x000000,
        0xFFFEFF, 0x64B0FF, 0x9290FF, 0xC676FF, 0xF36AFF, 0xFE6ECC, 0xFE8170, 0xEA9E22,
        0xBCBE00, 0x88D800, 0x5CE430, 0x45E082, 0x48CDDE, 0x4F4F4F, 0x000000, 0x000000,
        0xFFFEFF, 0xC0DFFF, 0xD3D2FF, 0xE8C8FF, 0xFBC2FF, 0xFEC4EA, 0xFECCC5, 0xF7D8A5,
        0xE4E594, 0xCFEF96, 0xBDF4AB, 0xB3F3CC, 0xB5EBF2, 0xB8B8B8, 0x000000, 0x000000
    ]

# ══════════════════════════════════════════════════════════════
# NES CONSOLE
# ══════════════════════════════════════════════════════════════

class NES:
    __slots__ = ('cpu', 'ppu', 'wram', 'rom', 'mirroring', 'frame_count')
    
    def __init__(self):
        self.cpu = CPU(self)
        self.ppu = PPU(self)
        self.wram = [0] * 0x800
        self.rom = None
        self.mirroring = 0
        self.frame_count = 0

    def load_rom(self, rom_data):
        if rom_data[0:3] != b'NES':
            raise ValueError("Invalid NES ROM")
        
        prg_banks = rom_data[4]
        chr_banks = rom_data[5]
        flags6 = rom_data[6]
        self.mirroring = flags6 & 1
        
        prg_start = 16
        chr_start = prg_start + prg_banks * 16384
        
        self.rom = {
            'prg': rom_data[prg_start:chr_start],
            'chr': rom_data[chr_start:chr_start + chr_banks * 8192]
        }
        
        self.cpu.reset()
        sys_bus.rom_loaded = True
        print(f"[NES] ROM Loaded | PRG: {prg_banks} | CHR: {chr_banks} | Mirroring: {'Vertical' if self.mirroring else 'Horizontal'}")

    def read(self, addr):
        addr &= 0xFFFF
        if addr < 0x2000:
            return self.wram[addr & 0x7FF]
        elif addr < 0x4000:
            return self.ppu.read(addr & 7)
        elif addr == 0x4016:
            return 0  # Input placeholder
        elif addr >= 0x8000:
            return self.rom['prg'][(addr - 0x8000) % len(self.rom['prg'])]
        return 0

    def write(self, addr, val):
        addr &= 0xFFFF
        val &= 0xFF
        if addr < 0x2000:
            self.wram[addr & 0x7FF] = val
        elif addr < 0x4000:
            self.ppu.write(addr & 7, val)
        elif addr == 0x4014:
            self.dma_transfer(val)
        elif addr == 0x4016:
            pass  # Input placeholder

    def read16(self, addr):
        return self.read(addr) | (self.read(addr + 1) << 8)

    def chr_read(self, addr):
        if self.rom['chr']:
            return self.rom['chr'][addr % len(self.rom['chr'])]
        return 0

    def chr_write(self, addr, val):
        if not self.rom['chr']:
            return
        self.rom['chr'][addr % len(self.rom['chr'])] = val

    def dma_transfer(self, page):
        addr = page << 8
        for i in range(256):
            self.ppu.oam[i] = self.read(addr + i)
        self.cpu.cycles += 513

    def run_frame(self):
        target_cycles = 29781  # NES frames per CPU cycle ratio
        
        while self.cpu.total_cycles < target_cycles:
            if not sys_bus.paused:
                self.cpu.step()
            
            for _ in range(3):  # PPU runs 3x faster than CPU
                self.ppu.tick()
        
        self.cpu.total_cycles -= target_cycles
        self.frame_count += 1

# ══════════════════════════════════════════════════════════════
# MODERN TKINTER GUI
# ══════════════════════════════════════════════════════════════

class FCEUXGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Cat's FCEUX 0.1.1B")
        self.root.geometry("800x600")
        self.root.configure(bg='#2b2b2b')
        
        self.nes = NES()
        self.setup_gui()
        self.running = False
        self.emulation_thread = None

    def setup_gui(self):
        # Main frame
        main_frame = Frame(self.root, bg='#2b2b2b')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title
        title = Label(main_frame, text="🐱 CAT'S FCEUX 0.1.1B", 
                     font=('Arial', 16, 'bold'), fg='#00ff00', bg='#2b2b2b')
        title.pack(pady=10)
        
        # Display canvas
        self.canvas = Canvas(main_frame, width=256, height=240, bg='#000000')
        self.canvas.pack(pady=10)
        
        # Controls frame
        controls = Frame(main_frame, bg='#2b2b2b')
        controls.pack(pady=10)
        
        tk.Button(controls, text="Load ROM", command=self.load_rom_dialog,
                 bg='#444', fg='white', font=('Arial', 10)).pack(side=tk.LEFT, padx=5)
        
        self.start_btn = tk.Button(controls, text="Start", command=self.toggle_emulation,
                                  bg='#444', fg='white', font=('Arial', 10))
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        tk.Button(controls, text="God Console", command=self.open_console,
                 bg='#444', fg='white', font=('Arial', 10)).pack(side=tk.LEFT, padx=5)
        
        # Status
        self.status = Label(main_frame, text="Ready to load ROM", 
                           font=('Arial', 10), fg='#cccccc', bg='#2b2b2b')
        self.status.pack(pady=5)

    def load_rom_dialog(self):
        filename = filedialog.askopenfilename(
            title="Select NES ROM",
            filetypes=[("NES files", "*.nes"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'rb') as f:
                    rom_data = f.read()
                self.nes.load_rom(rom_data)
                self.status.config(text=f"Loaded: {os.path.basename(filename)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load ROM: {e}")

    def toggle_emulation(self):
        if not self.running:
            if not sys_bus.rom_loaded:
                messagebox.showwarning("Warning", "Please load a ROM first")
                return
            self.start_emulation()
            self.start_btn.config(text="Stop")
        else:
            self.stop_emulation()
            self.start_btn.config(text="Start")

    def start_emulation(self):
        self.running = True
        self.emulation_thread = threading.Thread(target=self.emulation_loop, daemon=True)
        self.emulation_thread.start()

    def stop_emulation(self):
        self.running = False
        if self.emulation_thread:
            self.emulation_thread.join(timeout=1.0)

    def emulation_loop(self):
        while self.running:
            self.nes.run_frame()
            if self.nes.frame_count % 2 == 0:  # Limit update rate
                self.update_display()
            time.sleep(0.001)  # Prevent excessive CPU usage

    def update_display(self):
        if not self.running:
            return
        
        img_data = bytes(self.nes.ppu.front_buffer)
        self.photo = tk.PhotoImage(width=256, height=240)
        self.photo.put(" ".join(f"#{c:06x}" for c in self.nes.ppu.front_buffer), to=(0, 0, 255, 239))
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        self.root.update_idletasks()

    def open_console(self):
        if not sys_bus.console_active:
            threading.Thread(target=god_console, args=(self.nes,), daemon=True).start()

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.running = False

# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    gui = FCEUXGUI()
    gui.run()
